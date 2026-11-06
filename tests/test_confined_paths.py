"""Regressions #23/#24 : noms exacts, cibles physiques et substitutions de liens."""
from __future__ import annotations

import base64
import contextlib
import errno
import hashlib
import heapq
import io
import json
import os
from pathlib import Path
import queue
import select
import shlex
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import offline
from romeo_mcp import guard, file_operations, remote_reads, files, confined_transfers, remote_paths, remote_logs
from romeo_mcp.ssh import SSHError


class LiteralPaths(unittest.TestCase):
    def test_names_are_not_stripped_or_expanded_as_other_users(self):
        for name in ('file ', 'file\t', 'file\n', ' file', ' ', '\t', '~literal'):
            self.assertEqual(guard.check_path(name, '/home/test', '/scratch/test'), '/scratch/test/' + name)
        self.assertEqual(guard.check_path('~/file ', '/home/test', '/scratch/test'), '/home/test/file ')
        for name in ('', 'x\x00', 'x' * 4097, '/elsewhere/file'):
            with self.assertRaises(guard.GuardError):
                guard.check_path(name, '/home/test', '/scratch/test')


class ListingSnapshots(unittest.TestCase):
    """Run the listing body on Windows too; descriptor confinement is POSIX."""

    def entry(self, name, error=None, kind=stat.S_IFREG):
        entry = Mock()
        entry.name = name
        entry.stat.side_effect = error
        entry.stat.return_value = os.stat_result((kind | 0o600, 1, 1, 1, 1, 1, 11, 0, 0, 0))
        return entry

    def listing(self, entries, limit, open_error=None):
        code = remote_reads.LIST_DIRECTORY[len(remote_paths.CONFINED_PATHS):]
        output, exit_code = io.StringIO(), 0
        opened = Mock(return_value=123, side_effect=open_error)
        with patch.object(sys, 'argv', ['probe', '/fixture', str(limit), '["/fixture"]']), \
                patch.object(os, 'O_DIRECTORY', getattr(os, 'O_DIRECTORY', 0), create=True), \
                patch.object(os, 'scandir', return_value=contextlib.nullcontext(iter(entries))), \
                patch.object(os, 'close') as closed, contextlib.redirect_stdout(output):
            try:
                exec(compile(code, '<listing-body>', 'exec'), {'confined_open': opened})
            except SystemExit as exc:
                exit_code = exc.code
        if open_error is None:
            closed.assert_called_once_with(123)
        else:
            closed.assert_not_called()
        return json.loads(output.getvalue()), exit_code

    def test_disappeared_names_do_not_fail_or_refill_a_bounded_snapshot(self):
        vanished = self.entry('a-gone', FileNotFoundError(errno.ENOENT, 'removed'))
        present, beyond, last = (self.entry(name) for name in ('b-present', 'c-beyond', 'z-last'))
        result, exit_code = self.listing([last, beyond, present, vanished], 2)
        self.assertEqual(exit_code, 0)
        self.assertEqual([entry['name'] for entry in result['entries']], ['b-present'])
        self.assertEqual(result['disappeared_entries'], 1)
        self.assertTrue(result['truncated'])
        vanished.stat.assert_called_once_with(follow_symlinks=False)
        present.stat.assert_called_once_with(follow_symlinks=False)
        beyond.stat.assert_not_called()
        last.stat.assert_not_called()

    def test_all_selected_names_can_disappear_with_count_at_the_limit(self):
        vanished = [self.entry(str(n), FileNotFoundError(errno.ENOENT, 'removed')) for n in range(3)]
        beyond = self.entry('z-beyond')
        result, exit_code = self.listing([beyond, *vanished], 3)
        self.assertEqual(exit_code, 0)
        self.assertEqual(result, {'entries': [], 'truncated': True, 'disappeared_entries': 3})
        beyond.stat.assert_not_called()

    def test_permission_and_other_stat_errors_remain_errors(self):
        for error in (PermissionError(errno.EACCES, 'denied'), OSError(errno.EIO, 'I/O failure'),
                      NotADirectoryError(errno.ENOTDIR, 'invalid parent')):
            with self.subTest(error=type(error).__name__):
                result, exit_code = self.listing([self.entry('file', error)], 1)
                self.assertEqual(exit_code, 2)
                self.assertEqual(set(result), {'error'})
                self.assertIn(str(error), result['error'])

    def test_directory_absence_is_not_a_successful_empty_snapshot(self):
        result, exit_code = self.listing([], 5, FileNotFoundError(errno.ENOENT, 'absent directory'))
        self.assertEqual(exit_code, 2)
        self.assertEqual(set(result), {'error'})

    def test_stable_snapshot_preserves_names_and_metadata_with_zero_disappeared(self):
        entries = [self.entry('file \n'), self.entry('directory', kind=stat.S_IFDIR),
                   self.entry('symlink', kind=stat.S_IFLNK)]
        result, exit_code = self.listing(entries, 3)
        self.assertEqual(exit_code, 0)
        self.assertFalse(result['truncated'])
        self.assertEqual(result['disappeared_entries'], 0)
        listed = {entry['name']: entry for entry in result['entries']}
        self.assertEqual(set(listed), {'file \n', 'directory', 'symlink'})
        self.assertEqual(listed['file \n']['size'], '11')
        self.assertTrue(listed['directory']['is_dir'])
        self.assertFalse(listed['directory']['is_symlink'])
        self.assertTrue(listed['symlink']['is_symlink'])
        self.assertFalse(listed['symlink']['is_dir'])


@unittest.skipUnless(os.name == 'posix', 'descripteurs et liens POSIX ; aucun SSH dans cette suite')
class ConfinedPaths(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='romeo-confined-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.inside, self.outside = self.root/'inside', self.root/'outside'
        self.inside.mkdir()
        self.outside.mkdir()
        self.roots = [str(self.inside)]
        (self.outside/'file').write_text('outside-original')

    def execute(self, code, args):
        output = io.StringIO()
        handlers = {kind: signal.getsignal(kind) for kind in (signal.SIGTERM, signal.SIGHUP)}
        with patch.object(sys, 'argv', ['probe', *map(str, args)]), contextlib.redirect_stdout(output):
            try:
                exec(compile(code, '<remote-probe>', 'exec'), {})
            except SystemExit:
                pass
            finally:
                for kind, handler in handlers.items():
                    signal.signal(kind, handler)
        return json.loads(output.getvalue())

    def read(self, path, budget=100):
        return self.execute(remote_reads.READ_TEXT, [path, 1, 100, budget, json.dumps(self.roots)])

    def test_listing_survives_real_atomic_publication_after_enumeration(self):
        stage, target = self.inside/'.romeo-write-fixture', self.inside/'target'
        stage.write_text('complete-new-generation')
        target.write_text('old')
        native_nsmallest = heapq.nsmallest

        def publish_after_snapshot(*args, **kwargs):
            selected = native_nsmallest(*args, **kwargs)
            self.assertIn(stage.name, [entry.name for entry in selected])
            os.replace(stage, target)
            return selected

        with patch.object(heapq, 'nsmallest', side_effect=publish_after_snapshot):
            result = self.execute(remote_reads.LIST_DIRECTORY, [self.inside, 10, json.dumps(self.roots)])
        self.assertEqual([entry['name'] for entry in result['entries']], ['target'])
        self.assertEqual(result['disappeared_entries'], 1)
        self.assertFalse(result['truncated'])
        self.assertEqual(int(result['entries'][0]['size']), target.stat().st_size)
        self.assertEqual(target.read_text(), 'complete-new-generation')
        stable = self.execute(remote_reads.LIST_DIRECTORY, [self.inside, 10, json.dumps(self.roots)])
        self.assertEqual(stable['disappeared_entries'], 0)

    def test_listing_absent_directory_and_scan_permission_errors_are_refusals(self):
        args = [self.inside/'missing', 10, json.dumps(self.roots)]
        self.assertIn('error', self.execute(remote_reads.LIST_DIRECTORY, args))
        with patch.object(os, 'scandir', side_effect=PermissionError(errno.EACCES, 'denied')):
            result = self.execute(remote_reads.LIST_DIRECTORY, [self.inside, 10, json.dumps(self.roots)])
        self.assertIn('denied', result['error'])
        self.assertNotIn('entries', result)

    def test_listing_byte_names_and_symlinks_remain_exact(self):
        raw_name = b'raw-\xff'
        path = os.fsencode(self.inside) + b'/' + raw_name
        with open(path, 'wb') as output:
            output.write(b'bytes')
        (self.inside/'link').symlink_to(self.outside/'file')
        result = self.execute(remote_reads.LIST_DIRECTORY, [self.inside, 10, json.dumps(self.roots)])
        byte_entry = next(entry for entry in result['entries'] if 'name_bytes_base64' in entry)
        self.assertEqual(base64.b64decode(byte_entry['name_bytes_base64']), raw_name)
        link_entry = next(entry for entry in result['entries'] if entry['name'] == 'link')
        self.assertTrue(link_entry['is_symlink'])
        self.assertFalse(link_entry['is_dir'])
        self.assertEqual(result['disappeared_entries'], 0)

    def logs(self, path, **kwargs):
        request = dict(targets={'out': str(path)}, roots=self.roots, stream='out',
                       lines=10, max_chars=1000, max_files=10, pattern=None, max_bytes_per_file=1024)
        request.update(kwargs)
        return self.execute(remote_logs.READ_LOGS, [json.dumps(request)])

    def test_log_names_remain_data_and_cannot_execute_a_substitution(self):
        empty = self.inside/'empty.err'
        empty.touch()
        names = ['log$(printf${IFS}INJECTED>${f}.marker)', "quote'log\"", 'line\nlog',
                 '  spaces  ', 'literal[bracket]*']
        for name in names:
            path = self.inside/name
            path.write_text('MATCH: fictional\n')
            for pattern in (None, 'MATCH'):
                result = self.logs(path, targets={'out': str(path), 'err': str(empty)}, pattern=pattern)
                self.assertIn('MATCH: fictional', result['logs']['out'], result)
                self.assertFalse((self.inside/'empty.err.marker').exists())
                self.assertFalse(result['has_stderr_content'])

    def test_logs_reject_final_parent_and_direct_escape_for_tail_and_search(self):
        final, parent = self.inside/'final', self.inside/'parent'
        final.symlink_to(self.outside/'file')
        parent.symlink_to(self.outside, target_is_directory=True)
        for path in (final, parent/'file', self.outside/'file'):
            for pattern in (None, 'outside'):
                result = self.logs(path, pattern=pattern)
                self.assertIn('error', result)
                self.assertNotIn('outside-original', json.dumps(result))
        self.assertEqual((self.outside/'file').read_text(), 'outside-original')

    def test_log_internal_alias_and_globs_preserve_limits_and_stderr_presence(self):
        for index in range(3):
            (self.inside/('job_%d.out' % index)).write_text('OLD\nMATCH-one\nMATCH-two\n')
            (self.inside/('job_%d.err' % index)).write_text('stderr' if index == 2 else '')
        alias = self.root/'gpfs-alias'
        alias.symlink_to(self.inside, target_is_directory=True)
        targets = {'out': str(alias/'job_*.out'), 'err': str(alias/'job_*.err')}
        result = self.logs(alias/'job_*.out', targets=targets, max_files=1, lines=1, pattern='MATCH')
        self.assertIn('MATCH-one', result['logs']['out'])
        self.assertNotIn('MATCH-two', result['logs']['out'])
        self.assertTrue(result['files_limited'])
        self.assertTrue(result['has_stderr_content'])
        self.assertNotIn('job_1.out', result['logs']['out'])

    def test_log_fifo_socket_and_invalid_regex_are_bounded_refusals(self):
        import socket
        fifo = self.inside/'fifo'
        os.mkfifo(fifo)
        socket_path = self.inside/'socket'
        with socket.socket(socket.AF_UNIX) as server:
            previous = os.getcwd()
            try:
                os.chdir(self.inside)
                server.bind('socket')
            finally:
                os.chdir(previous)
            for path in (fifo, socket_path):
                request = dict(targets={'out': str(path)}, roots=self.roots, stream='out', lines=10,
                               max_chars=100, max_files=1, pattern=None, max_bytes_per_file=1024)
                result = subprocess.run([sys.executable, '-c', remote_logs.READ_LOGS, json.dumps(request)],
                                        capture_output=True, text=True, timeout=2)
                self.assertEqual(result.returncode, 2)
                self.assertIn('error', json.loads(result.stdout))
        self.assertIn('error', self.logs(self.inside/'missing', pattern='['))

    def test_log_tail_large_line_search_window_and_unicode_budget(self):
        path = self.inside/'large'
        path.write_text('OLD_MATCH\n' + '🧪' * 100000 + '\nNEW_MATCH\n')
        result = self.logs(path, max_chars=40, lines=1)
        self.assertIn('NEW_MATCH', result['logs']['out'])
        self.assertNotIn('🧪', result['logs']['out'])
        result = self.logs(path, max_chars=40, lines=2)
        self.assertTrue(result['clipped']['out'])
        self.assertLessEqual(len(result['logs']['out']), 40)
        result = self.logs(path, pattern='MATCH', max_bytes_per_file=20)
        self.assertIn('NEW_MATCH', result['logs']['out'])
        self.assertNotIn('OLD_MATCH', result['logs']['out'])

    def test_final_log_target_swap_cannot_redirect_the_read(self):
        path = self.inside/'file'
        path.write_text('inside-original')
        def swap():
            path.rename(self.inside/'held')
            path.symlink_to(self.outside/'file')
        with self.swapped_open(lambda name, kw: name == 'file' and 'dir_fd' in kw, swap):
            result = self.logs(path)
        self.assertIn('error', result)
        self.assertNotIn('outside-original', json.dumps(result))

    def write(self, path, action='create', content='new', expected=None):
        request = dict(path=str(path), roots=self.roots, action=action, expected=expected,
                       content=base64.b64encode(content.encode()).decode())
        return self.execute(file_operations._WRITE, [json.dumps(request)])

    def secret(self, name='fictional.env'):
        return self.execute(file_operations._SECRET, [json.dumps({'home': str(self.inside), 'name': name})])

    def test_read_fifo_without_writer_is_refused_immediately(self):
        fifo = self.inside/'fifo'
        os.mkfifo(fifo)
        result = subprocess.run([sys.executable, '-c', remote_reads.READ_TEXT,
            str(fifo), '1', '100', '100', json.dumps(self.roots)],
            capture_output=True, text=True, timeout=2)
        self.assertEqual(result.returncode, 2)
        self.assertIn('regulier', json.loads(result.stdout)['error'])
        self.assertIn('error', self.read(self.inside))

    def test_read_socket_and_device_are_refused(self):
        import socket
        with socket.socket(socket.AF_UNIX) as server:
            path = self.inside/'socket'
            # Le nom AF_UNIX est limite a environ 108 octets : les fixtures
            # peuvent avoir un parent long. Le nom relatif reste le meme inode.
            previous = os.getcwd()
            try:
                os.chdir(self.inside)
                server.bind('socket')
            finally:
                os.chdir(previous)
            self.assertIn('error', self.read(path))
        self.roots.append('/dev')
        self.assertIn('regulier', self.read('/dev/null')['error'])

    def test_secret_creates_private_file_and_preserves_existing_content(self):
        self.assertTrue(self.secret()['ok'])
        private = self.inside/'.romeo-mcp'
        target = private/'fictional.env'
        self.assertEqual(private.stat().st_mode & 0o777, 0o700)
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        target.write_text('FICTIONAL_KEY=untouched\n')
        target.chmod(0o644)
        private.chmod(0o755)
        self.assertTrue(self.secret()['ok'])
        self.assertEqual(target.read_text(), 'FICTIONAL_KEY=untouched\n')
        self.assertEqual(private.stat().st_mode & 0o777, 0o700)
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_secret_parent_and_final_links_are_refused_without_outside_chmod(self):
        private = self.inside/'.romeo-mcp'
        private.symlink_to(self.outside, target_is_directory=True)
        before = self.outside.stat().st_mode
        self.assertFalse(self.secret()['ok'])
        self.assertEqual(self.outside.stat().st_mode, before)
        self.assertFalse((self.outside/'fictional.env').exists())
        private.unlink()
        private.mkdir()
        target = private/'fictional.env'
        target.symlink_to(self.outside/'file')
        before = (self.outside/'file').stat().st_mode
        self.assertFalse(self.secret()['ok'])
        self.assertEqual((self.outside/'file').stat().st_mode, before)
        self.assertEqual((self.outside/'file').read_text(), 'outside-original')

    def test_secret_hardlink_and_fifo_are_refused(self):
        private = self.inside/'.romeo-mcp'
        private.mkdir()
        target = private/'fictional.env'
        os.link(self.outside/'file', target)
        before = (self.outside/'file').stat().st_mode
        self.assertFalse(self.secret()['ok'])
        self.assertEqual((self.outside/'file').stat().st_mode, before)
        target.unlink()
        os.mkfifo(target)
        self.assertFalse(self.secret()['ok'])

    def test_secret_parent_swap_keeps_original_descriptor(self):
        private = self.inside/'.romeo-mcp'
        private.mkdir()
        def swap():
            private.rename(self.inside/'held-private')
            private.symlink_to(self.outside, target_is_directory=True)
        with self.swapped_open(lambda name, kw: name == 'fictional.env', swap):
            self.assertTrue(self.secret()['ok'])
        self.assertTrue((self.inside/'held-private'/'fictional.env').is_file())
        self.assertFalse((self.outside/'fictional.env').exists())

    def test_secret_root_alias_is_permitted(self):
        alias = self.root/'home-alias'
        alias.symlink_to(self.inside, target_is_directory=True)
        result = self.execute(file_operations._SECRET, [json.dumps({'home': str(alias), 'name': 'fictional.env'})])
        self.assertTrue(result['ok'])

    def test_distinct_whitespace_names_survive_read_create_and_replace(self):
        (self.inside/'file').write_text('plain')
        for name in ('file ', 'file\t', 'file\n', ' file', ' '):
            path = self.inside/name
            self.assertTrue(self.write(path, content=name)['ok'])
            self.assertEqual(self.read(path)['content'], name)
            self.assertTrue(self.write(path, 'replace', 'replaced')['ok'])
            self.assertEqual(path.read_text(), 'replaced')
            self.assertEqual((self.inside/'file').read_text(), 'plain')

    def test_parent_escape_rejects_reads_listing_creation_and_replacement(self):
        link = self.inside/'escape'
        link.symlink_to(self.outside, target_is_directory=True)
        self.assertIn('error', self.read(link/'file'))
        self.assertIn('error', self.execute(remote_reads.LIST_DIRECTORY, [link, 10, json.dumps(self.roots)]))
        self.assertFalse(self.write(link/'new')['ok'])
        self.assertFalse(self.write(link/'file', 'replace')['ok'])
        self.assertFalse((self.outside/'new').exists())
        self.assertEqual((self.outside/'file').read_text(), 'outside-original')

    def test_directory_audit_refuses_physical_escape_before_shell_execution(self):
        (self.inside/'escape').symlink_to(self.outside, target_is_directory=True)
        request = dict(path=str(self.inside/'escape'), roots=self.roots,
                       command="printf '%s' '{\"ok\":true}'", timeout=5)
        self.assertFalse(self.execute(remote_paths.DIRECTORY_COMMAND, [json.dumps(request)])['ok'])
        request['path'] = str(self.inside)
        self.assertTrue(self.execute(remote_paths.DIRECTORY_COMMAND, [json.dumps(request)])['ok'])

    def test_directory_audit_keeps_original_directory_after_parent_swap(self):
        parent, swap = self.parent_fixture()
        request = dict(path=str(parent), roots=self.roots,
                       command='printf \'"\'; cat '+remote_paths.DIRECTORY_TARGET+'/file; printf \'"\'', timeout=5)
        native_popen = subprocess.Popen
        def swapped_popen(*args, **kwargs):
            swap()
            return native_popen(*args, **kwargs)
        with patch.object(subprocess, 'Popen', side_effect=swapped_popen):
            self.assertEqual(self.execute(remote_paths.DIRECTORY_COMMAND, [json.dumps(request)]), 'inside-original')
        self.assertEqual((self.outside/'file').read_text(), 'outside-original')

    def test_directory_audit_timeout_stops_its_process_group(self):
        import time
        request = dict(path=str(self.inside), roots=self.roots, command='sleep 10', timeout=.05)
        start = time.monotonic()
        self.assertFalse(self.execute(remote_paths.DIRECTORY_COMMAND, [json.dumps(request)])['ok'])
        self.assertLess(time.monotonic()-start, 2)

    def test_final_symlink_escape_and_existing_symlink_writes_are_refused(self):
        path = self.inside/'escape'
        path.symlink_to(self.outside/'file')
        self.assertIn('error', self.read(path))
        self.assertFalse(self.write(path)['ok'])
        self.assertFalse(self.write(path, 'replace')['ok'])
        self.assertEqual((self.outside/'file').read_text(), 'outside-original')

    def test_legitimate_root_and_internal_aliases_keep_working(self):
        (self.inside/'file').write_text('inside')
        alias = self.root/'gpfs-alias'
        alias.symlink_to(self.inside, target_is_directory=True)
        self.roots.append(str(alias))
        (self.inside/'internal').symlink_to(self.inside, target_is_directory=True)
        for path in (alias/'file', self.inside/'internal'/'file'):
            self.assertEqual(self.read(path)['content'], 'inside')
            self.assertTrue(self.write(path, 'replace', 'inside')['ok'])
        self.assertTrue(self.write(alias/'created')['ok'])

    def swapped_open(self, trigger, callback):
        native_open = os.open
        done = False
        def open_once(path, *args, **kwargs):
            nonlocal done
            if not done and trigger(path, kwargs):
                done = True
                callback()
            return native_open(path, *args, **kwargs)
        return patch.object(os, 'open', side_effect=open_once)

    def parent_fixture(self):
        parent = self.inside/'parent'
        parent.mkdir()
        (parent/'file').write_text('inside-original')
        def swap():
            parent.rename(self.inside/'held')
            parent.symlink_to(self.outside, target_is_directory=True)
        return parent, swap

    def test_directory_changed_to_symlink_before_open_is_refused(self):
        parent, swap = self.parent_fixture()
        with self.swapped_open(lambda name, kw: name == 'parent', swap):
            self.assertIn('error', self.read(parent/'file'))
        self.assertEqual((self.outside/'file').read_text(), 'outside-original')

    def test_parent_swapped_after_open_cannot_redirect_publication(self):
        parent, swap = self.parent_fixture()
        with self.swapped_open(lambda name, kw: name == '.romeo-mcp-files.lock', swap):
            self.assertTrue(self.write(parent/'file', 'replace')['ok'])
        self.assertEqual((self.inside/'held'/'file').read_text(), 'new')
        self.assertEqual((self.outside/'file').read_text(), 'outside-original')

    def test_final_target_swapped_before_read_cannot_be_followed(self):
        path = self.inside/'file'
        path.write_text('inside-original')
        def swap():
            path.rename(self.inside/'held')
            path.symlink_to(self.outside/'file')
        with self.swapped_open(lambda name, kw: name == 'file' and 'dir_fd' in kw, swap):
            self.assertIn('error', self.read(path))
        self.assertEqual((self.outside/'file').read_text(), 'outside-original')


class TransferGuardProtocolTests(unittest.TestCase):
    def guard(self):
        guard = confined_transfers.TransferGuard('offline', '/fixture/file', ['/fixture'],
                                                 'upload', 'source', bytes_total=100)
        guard.process = Mock(stdin=io.StringIO())
        return guard

    def assert_commit_refused(self, guard):
        self.assertTrue(guard.broken)
        written = guard.process.stdin.getvalue()
        with self.assertRaises(SSHError):
            guard.commit()
        self.assertEqual(guard.process.stdin.getvalue(), written)
        self.assertTrue(written)
        self.assertTrue(all(json.loads(line)['action'] == 'sample' for line in written.splitlines()))
        guard.process.stdout.readline.assert_not_called()

    def test_pending_sample_does_not_flood_or_expire_after_the_old_five_second_limit(self):
        guard = self.guard()
        with patch.object(time, 'monotonic', return_value=0):
            self.assertIsNone(guard.sample())
        with patch.object(time, 'monotonic', return_value=600):
            for _ in range(1000):
                self.assertIsNone(guard.sample())
            self.assertFalse(guard.broken)
            self.assertEqual(guard.request_id, 1)
            self.assertEqual(guard.pending_sample, 1)
            delayed = {'ok': True, 'kind': 'sample', 'request_id': 1,
                       'valid': True, 'bytes_present': 40, 'bytes_total': 100}
            guard.messages.put(json.dumps(delayed))
            received = guard.sample()
            self.assertEqual({key: received[key] for key in delayed}, delayed)
            self.assertEqual(received['observed_monotonic'], 0)
        self.assertIsNone(guard.pending_sample)
        self.assertEqual([json.loads(line) for line in guard.process.stdin.getvalue().splitlines()],
                         [{'action': 'sample', 'request_id': 1}])

    def test_sample_keeps_its_local_send_time_when_a_delayed_response_claims_another_time(self):
        guard = self.guard()
        stream = guard.process.stdin
        guard.process.stdin = Mock(wraps=stream)

        def send(line):
            request = json.loads(line)
            self.assertEqual(guard.sample_times[request['request_id']], (1000, 10))
            return stream.write(line)

        guard.process.stdin.write.side_effect = send
        with patch.object(time, 'time', return_value=1000), patch.object(time, 'monotonic', return_value=10):
            self.assertIsNone(guard.sample())
        guard.messages.put(json.dumps({'ok': True, 'kind': 'sample', 'request_id': 1,
                                       'valid': True, 'bytes_present': 40, 'bytes_total': 100,
                                       'observed_at': 99999, 'observed_monotonic': 99999}))
        with patch.object(time, 'time', return_value=1030), patch.object(time, 'monotonic', return_value=40):
            received = guard.sample()
        self.assertEqual(received['observed_at'], 1000)
        self.assertEqual(received['observed_monotonic'], 10)
        self.assertEqual(guard.sample_times, {})

    def test_invalid_or_unrelated_pending_response_prevents_poll_and_commit(self):
        responses = [None, 'not JSON', '[]',
                     json.dumps({'ok': True, 'kind': 'commit', 'request_id': 1}),
                     json.dumps({'ok': True, 'kind': 'sample', 'request_id': 2}),
                     json.dumps({'ok': False, 'kind': 'sample', 'request_id': 1, 'error': 'fixture refusal'}),
                     json.dumps({'ok': 1, 'kind': 'sample', 'request_id': 1})]
        for response in responses:
            for action in ('poll', 'commit'):
                with self.subTest(response=response, action=action):
                    guard = self.guard()
                    self.assertIsNone(guard.sample())
                    guard.messages.put(response)
                    with self.assertRaises(SSHError):
                        guard.sample() if action == 'poll' else guard.commit()
                    self.assert_commit_refused(guard)

    def test_sample_timeout_breaks_channel_and_prevents_commit(self):
        guard = self.guard()
        with self.assertRaises(SSHError):
            guard._exchange('sample', timeout=.01)
        self.assert_commit_refused(guard)

    def test_final_sample_drains_the_old_partial_response_then_requests_a_fresh_one(self):
        guard = self.guard()
        self.assertIsNone(guard.sample())
        guard.messages.put(json.dumps({'ok': True, 'kind': 'sample', 'request_id': 1,
                                       'valid': True, 'bytes_present': 40, 'bytes_total': 100}))
        stream = guard.process.stdin
        guard.process.stdin = Mock(wraps=stream)
        final = {'ok': True, 'kind': 'sample', 'request_id': 2,
                 'valid': True, 'bytes_present': 100, 'bytes_total': 100}

        def request_fresh(line):
            packet = json.loads(line)
            self.assertIsNone(guard.pending_sample)
            self.assertEqual(packet, {'action': 'sample', 'request_id': 2})
            written = stream.write(line)
            guard.messages.put(json.dumps(final))
            return written

        guard.process.stdin.write.side_effect = request_fresh
        received = guard.finish_sample()
        self.assertEqual({key: received[key] for key in final}, final)
        self.assertIsNone(guard.pending_sample)
        self.assertEqual([json.loads(line) for line in stream.getvalue().splitlines()],
                         [{'action': 'sample', 'request_id': 1}, {'action': 'sample', 'request_id': 2}])

    def test_commit_drains_a_pending_sample_before_writing_its_own_request(self):
        guard = self.guard()
        self.assertIsNone(guard.sample())
        guard.messages.put(json.dumps({'ok': True, 'kind': 'sample', 'request_id': 1,
                                       'valid': False, 'bytes_present': None, 'bytes_total': 100}))
        stream = guard.process.stdin
        guard.process.stdin = Mock(wraps=stream)

        def publish(line):
            packet = json.loads(line)
            self.assertIsNone(guard.pending_sample)
            self.assertEqual(packet['action'], 'commit')
            self.assertEqual(packet['request_id'], 2)
            written = stream.write(line)
            guard.messages.put(json.dumps({'ok': True, 'kind': 'commit', 'request_id': 2, 'sha256': None}))
            return written

        guard.process.stdin.write.side_effect = publish
        committed = guard.commit()
        self.assertEqual(committed['kind'], 'commit')
        self.assertEqual(committed['request_id'], 2)
        self.assertEqual([json.loads(line)['action'] for line in stream.getvalue().splitlines()],
                         ['sample', 'commit'])

    def test_drain_and_final_sample_check_cancellation_between_bounded_queue_reads(self):
        class ProbeCancelled(RuntimeError):
            pass

        for pending in (False, True):
            with self.subTest(pending=pending):
                guard = self.guard()
                if pending:
                    self.assertIsNone(guard.sample())
                cancelled = [False]

                def check_cancelled():
                    if cancelled[0]:
                        raise ProbeCancelled('local cancellation witness')

                def no_response(*, timeout):
                    self.assertLessEqual(timeout, .25)
                    cancelled[0] = True
                    raise queue.Empty()

                guard.messages = Mock(get=Mock(side_effect=no_response))
                token = files._CANCEL_CHECK.set(check_cancelled)
                try:
                    began = time.monotonic()
                    with self.assertRaises(ProbeCancelled):
                        guard.finish_sample()
                    self.assertLessEqual(time.monotonic() - began, .25)
                finally:
                    files._CANCEL_CHECK.reset(token)
                guard.messages.get.assert_called_once()
                self.assert_commit_refused(guard)


@unittest.skipUnless(os.name == 'posix', 'superviseur POSIX et /proc ; aucun SSH dans cette suite')
class ConfinedTransfers(unittest.TestCase):
    def setUp(self):
        ConfinedPaths.setUp(self)
        self.native_popen = subprocess.Popen
        def supervisor(argv, **kwargs):
            words = shlex.split(argv[-1])
            return self.native_popen([sys.executable, '-u', '-c', words[3], words[4]], **kwargs)
        self.enterContext(patch.object(confined_transfers.subprocess, 'Popen', side_effect=supervisor))

    @contextlib.contextmanager
    def supervisor(self, direction, path, *, recursive=False, verify=True):
        """Exercise the remote protocol in a real local process, without SSH."""
        request = dict(path=str(path), roots=self.roots, direction=direction,
                       basename=Path(path).name, recursive=recursive, verify=verify,
                       lock_root=str(self.root/'locks'),
                       bytes_total=100 if direction == 'upload' else None)
        process = self.native_popen(
            [sys.executable, '-u', '-c', confined_transfers.SUPERVISOR, json.dumps(request)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding='utf-8')
        try:
            yield process, self.receive(process)
        finally:
            process.stdin.close()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=3)
            process.stdout.close()
            process.stderr.close()

    def receive(self, process):
        self.assertTrue(select.select([process.stdout], [], [], 5)[0],
                        'Le superviseur local ne repond pas.')
        line = process.stdout.readline()
        self.assertTrue(line, 'Le superviseur local a ferme sa sortie.')
        return json.loads(line)

    def request(self, process, action, request_id, **values):
        process.stdin.write(json.dumps(dict(action=action, request_id=request_id, **values)) + '\n')
        process.stdin.flush()
        response = self.receive(process)
        self.assertEqual(response.get('kind'), action, response)
        self.assertEqual(response.get('request_id'), request_id, response)
        return response

    def test_local_source_invalidation_leaves_pending_sample_for_unverified_commit_to_drain(self):
        source, target = self.root/'local-source', self.inside/'destination'
        source.write_bytes(b'original')
        original = files._source_signature(source)
        with confined_transfers.TransferGuard('offline', str(target), self.roots, 'upload',
                                               source.name, verify=False, bytes_total=8) as guard:
            with files.transfer_runner(lambda *_: self.fail('Aucun processus de copie attendu')):
                probe = files._upload_probe(guard, source, original)
                with patch.object(guard.messages, 'get_nowait', side_effect=queue.Empty):
                    self.assertIsNone(probe.sample())
                self.assertEqual(guard.pending_sample, 1)
                source.write_bytes(b'changed!')
                os.utime(source, ns=(source.stat().st_atime_ns, original[3] + 5_000_000_000))
                self.assertIsNone(probe.sample())
                self.assertTrue(probe.invalid)
                self.assertEqual(guard.pending_sample, 1)
                Path(guard.ready['proxy']).write_bytes(source.read_bytes())
                committed = guard.commit()
                self.assertTrue(committed['ok'], committed)
                self.assertEqual(committed['kind'], 'commit')
                self.assertEqual(committed['request_id'], 2)
                self.assertIsNone(committed['sha256'])
                self.assertIsNone(guard.pending_sample)
        self.assertEqual(target.read_bytes(), b'changed!')
        self.assertFalse(list(self.inside.rglob('.romeo-transfer-*')))

    def test_supervisor_samples_only_its_private_payload_and_preserves_commit_integrity(self):
        target = self.inside/'file'
        target.write_bytes(b'original')
        with self.supervisor('upload', target) as (process, ready):
            self.assertTrue(ready['ok'], ready)
            self.assertEqual(ready['kind'], 'ready')
            absent = self.request(process, 'sample', 17, path=str(self.outside/'file'))
            self.assertTrue(absent['valid'], absent)
            self.assertEqual(absent['bytes_present'], 0)
            payload = Path(ready['proxy'])
            payload.write_bytes(b'copy')
            first = self.request(process, 'sample', 18, path=str(self.outside/'file'))
            self.assertTrue(first['valid'], first)
            self.assertEqual(first['bytes_present'], 4)
            self.assertEqual(first['bytes_total'], 100)
            with payload.open('ab') as stream:
                stream.write(b'-complete')
            second = self.request(process, 'sample', 19)
            self.assertTrue(second['valid'], second)
            self.assertEqual(second['bytes_present'], len(b'copy-complete'))
            committed = self.request(process, 'commit', 20,
                                     expected_sha256=hashlib.sha256(b'copy-complete').hexdigest())
            self.assertTrue(committed['ok'], committed)
            self.assertEqual(committed['sha256'], hashlib.sha256(b'copy-complete').hexdigest())
        self.assertEqual(target.read_bytes(), b'copy-complete')
        self.assertEqual((self.outside/'file').read_text(), 'outside-original')
        self.assertFalse(list(self.inside.rglob('.romeo-transfer-*')))

    def test_supervisor_sample_remains_anchored_when_the_parent_path_is_replaced(self):
        parent, swap = ConfinedPaths.parent_fixture(self)
        with self.supervisor('upload', parent/'file') as (process, ready):
            payload = Path(ready['proxy'])
            payload.write_bytes(b'new')
            self.assertEqual(self.request(process, 'sample', 1)['bytes_present'], 3)
            swap()
            with payload.open('ab') as stream:
                stream.write(b'-copy')
            sampled = self.request(process, 'sample', 2)
            self.assertTrue(sampled['valid'], sampled)
            self.assertEqual(sampled['bytes_present'], 8)
            self.assertTrue(self.request(process, 'commit', 3)['ok'])
        self.assertEqual((self.inside/'held'/'file').read_bytes(), b'new-copy')
        self.assertEqual((self.outside/'file').read_text(), 'outside-original')

    def test_supervisor_rejects_special_payloads_without_following_or_waiting(self):
        for kind in ('symlink', 'fifo'):
            with self.subTest(kind=kind), self.supervisor('upload', self.inside/kind) as (process, ready):
                payload = Path(ready['proxy'])
                if kind == 'symlink':
                    payload.symlink_to(self.outside/'file')
                else:
                    os.mkfifo(payload)
                sampled = self.request(process, 'sample', 1)
                self.assertFalse(sampled['valid'], sampled)
        self.assertEqual((self.outside/'file').read_text(), 'outside-original')
        self.assertFalse(list(self.inside.rglob('.romeo-transfer-*')))

    def test_supervisor_latches_payload_regression_or_inode_replacement_as_unmeasurable(self):
        for change in ('shrink', 'replace'):
            with self.subTest(change=change), self.supervisor('upload', self.inside/change) as (process, ready):
                payload = Path(ready['proxy'])
                payload.write_bytes(b'12345678')
                self.assertTrue(self.request(process, 'sample', 1)['valid'])
                if change == 'replace':
                    payload.rename(payload.with_name('old-payload'))
                payload.write_bytes(b'123')
                self.assertFalse(self.request(process, 'sample', 2)['valid'])
                payload.write_bytes(b'123456789')
                self.assertFalse(self.request(process, 'sample', 3)['valid'])
        self.assertFalse((self.inside/'shrink').exists())
        self.assertFalse((self.inside/'replace').exists())

    def test_supervisor_download_uses_held_source_and_invalidates_changed_content(self):
        for verify in (False, True):
            with self.subTest(verify=verify):
                parent = self.inside/('source-parent-' + str(verify))
                held = self.inside/('held-parent-' + str(verify))
                parent.mkdir()
                source = parent/'file'
                source.write_bytes(b'original')
                with self.supervisor('download', source, verify=verify) as (process, ready):
                    self.assertEqual(ready['kind'], 'ready')
                    self.assertEqual(ready['bytes_total'], 8)
                    first = self.request(process, 'sample', 1, path=str(self.outside/'file'))
                    self.assertTrue(first['valid'], first)
                    self.assertEqual(first['bytes_total'], 8)
                    self.assertIsNone(first['bytes_present'])
                    parent.rename(held)
                    parent.symlink_to(self.outside, target_is_directory=True)
                    self.assertEqual(Path(ready['proxy']).read_bytes(), b'original')
                    self.assertTrue(self.request(process, 'sample', 2)['valid'])
                    (held/'file').write_bytes(b'changed!')
                    self.assertFalse(self.request(process, 'sample', 3)['valid'])
                    (held/'file').write_bytes(b'original')
                    self.assertFalse(self.request(process, 'sample', 4)['valid'])
                    (held/'file').write_bytes(b'changed!')
                    committed = self.request(process, 'commit', 5)
                    self.assertEqual(committed['ok'], not verify, committed)
                    if not verify:
                        self.assertIsNone(committed['sha256'])
        self.assertEqual((self.outside/'file').read_text(), 'outside-original')

    def test_empty_source_has_no_numeric_progress(self):
        source = self.inside/'empty'
        source.touch()
        with self.supervisor('download', source, verify=False) as (process, ready):
            self.assertIsNone(ready['bytes_total'])
            self.assertFalse(self.request(process, 'sample', 1)['valid'])

    def test_file_transfer_uses_held_descriptors_after_parent_swap(self):
        parent, swap = ConfinedPaths.parent_fixture(self)
        local = self.root/'local'
        local.write_text('new')
        def upload(argv, what):
            swap()
            Path(argv[-1].split(':', 1)[1]).write_bytes(local.read_bytes())
        with files.confined_paths(self.roots), patch.object(files, '_run', side_effect=upload):
            result = files.upload('offline', str(local), str(parent/'file'))
        self.assertTrue(result['remote_sha256'])
        self.assertEqual((self.inside/'held'/'file').read_text(), 'new')
        self.assertEqual((self.outside/'file').read_text(), 'outside-original')
        self.assertFalse(list(self.inside.rglob('.romeo-transfer-*')))

    def test_file_download_uses_original_inode_after_parent_swap(self):
        parent, swap = ConfinedPaths.parent_fixture(self)
        local = self.root/'downloaded'
        def download(argv, what):
            swap()
            Path(argv[-1]).write_bytes(Path(argv[-2].split(':', 1)[1]).read_bytes())
        with files.confined_paths(self.roots), patch.object(files, '_run', side_effect=download):
            result = files.download('offline', str(parent/'file'), str(local))
        self.assertTrue(result['remote_sha256'])
        self.assertEqual(local.read_text(), 'inside-original')

    def test_transfer_escape_is_refused_before_copy(self):
        (self.inside/'escape').symlink_to(self.outside, target_is_directory=True)
        source = self.root/'local'
        source.write_text('new')
        with files.confined_paths(self.roots), patch.object(files, '_run') as copy:
            for direction in ('upload', 'download'):
                with self.assertRaisesRegex(SSHError, 'Cible physique'):
                    if direction == 'upload':
                        files.upload('offline', str(source), str(self.inside/'escape'/'file'))
                    else:
                        files.download('offline', str(self.inside/'escape'/'file'), str(source))
            copy.assert_not_called()
        self.assertEqual((self.outside/'file').read_text(), 'outside-original')

    def test_copy_failure_removes_private_staging_and_keeps_original(self):
        source = self.root/'local'
        source.write_text('new')
        target = self.inside/'file'
        target.write_text('original')
        with files.confined_paths(self.roots), patch.object(files, '_run', side_effect=RuntimeError('fixture failed')):
            with self.assertRaises(RuntimeError):
                files.upload('offline', str(source), str(target))
        self.assertEqual(target.read_text(), 'original')
        self.assertFalse(list(self.inside.rglob('.romeo-transfer-*')))

    def test_cancellation_during_preparation_stops_before_scp_and_cleans_staging(self):
        source = self.root/'local'
        source.write_text('new')
        def cancelled():
            raise RuntimeError('fixture cancellation')
        with files.confined_paths(self.roots), files.transfer_runner(lambda *_: self.fail('SCP started'), cancelled):
            with self.assertRaisesRegex(RuntimeError, 'fixture cancellation'):
                files.upload('offline', str(source), str(self.inside/'file'))
        self.assertFalse((self.inside/'file').exists())
        self.assertFalse(list(self.inside.rglob('.romeo-transfer-*')))


if __name__ == '__main__':
    unittest.main(verbosity=2)
