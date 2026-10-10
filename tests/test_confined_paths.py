"""Regressions #23/#24 : noms exacts, cibles physiques et substitutions de liens."""
from __future__ import annotations

import base64
import contextlib
import io
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import offline
from romeo_mcp import guard, file_operations, remote_reads, files, confined_transfers, remote_paths
from romeo_mcp.ssh import SSHError


class LiteralPaths(unittest.TestCase):
    def test_names_are_not_stripped_or_expanded_as_other_users(self):
        for name in ('file ', 'file\t', 'file\n', ' file', ' ', '\t', '~literal'):
            self.assertEqual(guard.check_path(name, '/home/test', '/scratch/test'), '/scratch/test/' + name)
        self.assertEqual(guard.check_path('~/file ', '/home/test', '/scratch/test'), '/home/test/file ')
        for name in ('', 'x\x00', 'x' * 4097, '/elsewhere/file'):
            with self.assertRaises(guard.GuardError):
                guard.check_path(name, '/home/test', '/scratch/test')


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

    def write(self, path, action='create', content='new', expected=None):
        request = dict(path=str(path), roots=self.roots, action=action, expected=expected,
                       content=base64.b64encode(content.encode()).decode())
        return self.execute(file_operations._WRITE, [json.dumps(request)])

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


@unittest.skipUnless(os.name == 'posix', 'superviseur POSIX et /proc ; aucun SSH dans cette suite')
class ConfinedTransfers(unittest.TestCase):
    def setUp(self):
        ConfinedPaths.setUp(self)
        native_popen = subprocess.Popen
        def supervisor(argv, **kwargs):
            words = shlex.split(argv[-1])
            return native_popen([sys.executable, '-u', '-c', words[3], words[4]], **kwargs)
        self.enterContext(patch.object(confined_transfers.subprocess, 'Popen', side_effect=supervisor))

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
            local.write_bytes(Path(argv[-2].split(':', 1)[1]).read_bytes())
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
