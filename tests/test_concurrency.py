"""Real process/thread collisions; no SSH, Slurm or external files."""
from __future__ import annotations

import asyncio
import base64
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import offline
from romeo_mcp import config, files, checkpoint_storage, confined_transfers, file_operations
from romeo_mcp.resource_locks import ResourceBusy, ResourceLease
from romeo_mcp.profiles import ProfiledServer
from romeo_mcp.ssh import SSHError


class Reservations(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='romeo-concurrency-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.cache = self.root / 'leases'
        self.enterContext(patch.dict(os.environ, {'ROMEO_CONCURRENCY_ROOT': str(self.cache)}))
        self.target = self.root / 'target'
        self.target.write_text('original')

    def try_other(self, entries):
        def attempt():
            try:
                with ResourceLease(entries):
                    return True
            except ResourceBusy:
                return False
        with ThreadPoolExecutor(1) as pool:
            return pool.submit(attempt).result(timeout=10)

    def test_readers_coexist_but_both_writer_directions_are_refused(self):
        with ResourceLease([(self.target, False)]):
            self.assertTrue(self.try_other([(self.target, False)]))
            self.assertFalse(self.try_other([(self.target, True)]))
        with ResourceLease([(self.target, True)]):
            self.assertFalse(self.try_other([(self.target, False)]))
            self.assertFalse(self.try_other([(self.target, True)]))
        self.assertTrue(self.try_other([(self.target, True)]))

    def test_directory_descendants_conflict_but_siblings_do_not(self):
        directory = self.root / 'tree'
        directory.mkdir()
        child = directory / 'child'
        sibling = self.root / 'sibling'
        with ResourceLease([(directory, True)]):
            self.assertFalse(self.try_other([(child, True)]))
            self.assertFalse(self.try_other([(child, False)]))
            self.assertTrue(self.try_other([(sibling, True)]))
        with ResourceLease([(child, True)]):
            self.assertFalse(self.try_other([(directory, False)]))
            self.assertFalse(self.try_other([(directory, True)]))

    def test_hardlink_and_resolved_aliases_share_the_reservation(self):
        alias = self.root / 'hardlink'
        os.link(self.target, alias)
        with ResourceLease([(self.target, True)]):
            self.assertFalse(self.try_other([(alias, True)]))
            self.assertFalse(self.try_other([(self.root / 'unused' / '..' / 'target', False)]))

    def test_real_process_owner_crash_is_recovered_without_a_timeout(self):
        code = ('import sys; from romeo_mcp.resource_locks import ResourceLease; '
                'lease=ResourceLease([(sys.argv[1],True)]); lease.__enter__(); '
                'print("ready",flush=True); sys.stdin.readline()')
        child = subprocess.Popen([sys.executable, '-c', code, str(self.target)],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True, cwd=Path(__file__).resolve().parents[1])
        try:
            self.assertEqual(child.stdout.readline().strip(), 'ready')
            self.assertFalse(self.try_other([(self.target, True)]))
            child.kill()
            child.wait(timeout=10)
            self.assertTrue(self.try_other([(self.target, True)]))
            with closing(sqlite3.connect(self.cache / 'resources.db')) as connection:
                self.assertEqual(connection.execute('SELECT COUNT(*) FROM leases').fetchone()[0], 0)
            self.assertEqual(list(self.cache.glob('*.lock')), [])
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=10)
            for stream in (child.stdin, child.stdout, child.stderr):
                stream.close()

    def test_complete_resource_set_is_reserved_without_deadlock_or_partial_claim(self):
        other = self.root / 'other'
        with ResourceLease([(self.target, True)]):
            self.assertFalse(self.try_other([(other, True), (self.target, False)]))
            self.assertTrue(self.try_other([(other, True)]))
        with ResourceLease([(self.target, False)]):
            # Nested checks by the same operation must not conflict with itself.
            with ResourceLease([(self.target, False), (other, True)]):
                self.assertFalse(self.try_other([(other, True)]))

    def test_config_conflict_cannot_silently_drop_a_successful_update(self):
        entered, release = threading.Event(), threading.Event()
        profile = self.root / 'config.json'
        profile.write_text('{}')
        original = config.load
        def slow_load():
            value = original()
            entered.set()
            self.assertTrue(release.wait(10))
            return value
        with patch.dict(os.environ, {'ROMEO_CONFIG': str(profile)}), patch.object(config, 'load', slow_load):
            with ThreadPoolExecutor(1) as pool:
                first = pool.submit(config.save, {'ROMEO_HOST': 'fictional-host'})
                try:
                    self.assertTrue(entered.wait(10))
                    with self.assertRaises(ResourceBusy):
                        config.save({'ROMEO_QOS': 'normal'})
                finally:
                    release.set()
                first.result(timeout=10)
        with patch.dict(os.environ, {'ROMEO_CONFIG': str(profile)}):
            config.save({'ROMEO_QOS': 'normal'})
        self.assertEqual(json.loads(profile.read_text()), {'ROMEO_HOST': 'fictional-host', 'ROMEO_QOS': 'normal'})

    def test_download_collision_is_refused_and_original_is_visible_until_publication(self):
        entered, release = threading.Event(), threading.Event()
        copies = []
        def copy(argv, what):
            staged = Path(argv[-1])
            staged.write_text('new')
            copies.append(staged)
            entered.set()
            self.assertTrue(release.wait(10))
            return ''
        with patch.object(files, '_has_rsync', return_value=False), patch.object(files, '_run', copy):
            with ThreadPoolExecutor(1) as pool:
                first = pool.submit(files.download, 'invalid-offline-host', '/fictional/file', str(self.target))
                try:
                    self.assertTrue(entered.wait(10))
                    self.assertEqual(self.target.read_text(), 'original')
                    with self.assertRaises(ResourceBusy):
                        files.download('invalid-offline-host', '/fictional/file', str(self.target))
                    self.assertFalse(self.try_other([(self.target, False)]))
                finally:
                    release.set()
                first.result(timeout=10)
        self.assertEqual(self.target.read_text(), 'new')
        self.assertEqual(len(copies), 1)
        self.assertEqual(list(self.root.glob('.romeo-download-*')), [])

    def test_failed_copy_and_external_destination_change_preserve_the_original(self):
        def failed(argv, what):
            Path(argv[-1]).write_text('incomplete')
            raise SSHError('fictional copy failure')
        def changed(argv, what):
            Path(argv[-1]).write_text('new')
            self.target.write_text('external edit')
            return ''
        with patch.object(files, '_has_rsync', return_value=False):
            with patch.object(files, '_run', failed), self.assertRaises(SSHError):
                files.download('invalid-offline-host', '/fictional/file', str(self.target))
            self.assertEqual(self.target.read_text(), 'original')
            with patch.object(files, '_run', changed), self.assertRaisesRegex(SSHError, 'change'):
                files.download('invalid-offline-host', '/fictional/file', str(self.target))
            self.assertEqual(self.target.read_text(), 'external edit')
        self.assertEqual(list(self.root.glob('.romeo-download-*')), [])

    def test_independent_downloads_in_the_same_directory_really_overlap(self):
        barrier = threading.Barrier(2)
        def copy(argv, what):
            barrier.wait(timeout=10)
            Path(argv[-1]).write_text('complete')
            return ''
        with patch.object(files, '_has_rsync', return_value=False), patch.object(files, '_run', copy):
            with ThreadPoolExecutor(2) as pool:
                results = list(pool.map(lambda name: files.download('invalid-offline-host', '/fictional/'+name,
                                                                   str(self.root / name)), ['one', 'two']))
        self.assertEqual(len(results), 2)
        self.assertEqual((self.root / 'one').read_text(), 'complete')
        self.assertEqual((self.root / 'two').read_text(), 'complete')

    def test_recursive_download_to_existing_directory_keeps_scp_layout(self):
        directory = self.root / 'results'
        directory.mkdir()
        def copy(argv, what):
            payload = Path(argv[-1])
            payload.mkdir()
            (payload / 'one').write_text('complete')
            return ''
        with patch.object(files, '_has_rsync', return_value=False), patch.object(files, '_run', copy):
            response = files.download('invalid-offline-host', '/fictional/run', str(directory), True)
        self.assertEqual(response['to'], str(directory / 'run'))
        self.assertEqual((directory / 'run' / 'one').read_text(), 'complete')

    def test_checkpoint_lock_inode_survives_and_releases_when_owner_exits(self):
        path = self.root / '.protection.lock'
        path.touch()  # A stale marker from the previous implementation.
        with checkpoint_storage.protection_lock(path):
            def contender():
                with checkpoint_storage.protection_lock(path):
                    return True
            with ThreadPoolExecutor(1) as pool, self.assertRaises(OSError):
                pool.submit(contender).result(timeout=10)
        inode = path.stat().st_ino
        with checkpoint_storage.protection_lock(path):
            self.assertEqual(path.stat().st_ino, inode)

    def test_download_checksum_mismatch_and_cancellation_do_not_publish(self):
        def corrupt(*args):
            Path(args[2]).write_text('corrupt')
            return {'remote_sha256': '0' * 64}
        with patch.object(files, '_download', side_effect=corrupt), self.assertRaisesRegex(SSHError, 'Empreinte'):
            files.download('invalid-offline-host', '/fictional/file', str(self.target))
        self.assertEqual(self.target.read_text(), 'original')
        def cancel():
            raise SSHError('fictional cancellation')
        token = files._CANCEL_CHECK.set(cancel)
        try:
            with patch.object(files, '_download', side_effect=corrupt), self.assertRaisesRegex(SSHError, 'cancellation'):
                files.download('invalid-offline-host', '/fictional/file', str(self.target))
        finally:
            files._CANCEL_CHECK.reset(token)
        self.assertEqual(self.target.read_text(), 'original')
        self.assertEqual(list(self.root.glob('.romeo-download-*')), [])

    def test_cleanup_failure_does_not_turn_completed_work_into_a_never_started_refusal(self):
        lease = ResourceLease([(self.target, True)])
        with lease:
            self.target.write_text('completed')
            with patch.object(lease, '_transaction', side_effect=ResourceBusy('cache busy')):
                lease.__exit__(None, None, None)
        self.assertEqual(self.target.read_text(), 'completed')
        self.assertTrue(self.try_other([(self.target, True)]))

    def test_reservation_capacity_refuses_before_execution_and_recovers(self):
        leases = []
        try:
            for number in range(128):
                lease = ResourceLease([('action:capacity:' + str(number), True)])
                lease.__enter__()
                leases.append(lease)
            with self.assertRaisesRegex(ResourceBusy, 'Trop de reservations'):
                with ResourceLease([('action:capacity:overflow', True)]):
                    self.fail('overflow reservation started')
        finally:
            for lease in reversed(leases):
                lease.__exit__(None, None, None)
        self.assertTrue(self.try_other([(self.target, True)]))

    def test_two_workers_cannot_own_the_same_transfer_plan(self):
        from romeo_mcp import transfer_worker
        entered, release = threading.Event(), threading.Event()
        calls = []
        def controlled(path):
            calls.append(path)
            entered.set()
            self.assertTrue(release.wait(10))
        with patch.object(transfer_worker, '_run_owned', side_effect=controlled), ThreadPoolExecutor(1) as pool:
            first = pool.submit(transfer_worker.run, self.root / 'plan.json')
            try:
                self.assertTrue(entered.wait(10))
                with self.assertRaises(ResourceBusy):
                    transfer_worker.run(self.root / 'plan.json')
            finally:
                release.set()
            first.result(timeout=10)
        self.assertEqual(len(calls), 1)

    def test_checkpoint_protections_to_different_backups_still_share_the_source(self):
        entered, release = threading.Event(), threading.Event()
        calls = []
        source = self.root / 'checkpoints'
        (source/'same-run').mkdir(parents=True)
        checkpoint = {'manifest': {'run_id': 'same-run'}}
        def controlled(*args, **kwargs):
            calls.append(args)
            entered.set()
            self.assertTrue(release.wait(10))
            return {'ok': True}
        with patch.object(checkpoint_storage, 'copy_verified', side_effect=controlled), \
             patch.object(checkpoint_storage, 'retain_protected', return_value={}), ThreadPoolExecutor(1) as pool:
            first = pool.submit(checkpoint_storage.protect, checkpoint, source, self.root/'backup-one', {})
            try:
                self.assertTrue(entered.wait(10))
                with self.assertRaises(ResourceBusy):
                    checkpoint_storage.protect(checkpoint, source, self.root/'backup-two', {})
                self.assertFalse((self.root/'backup-two').exists())
            finally:
                release.set()
            self.assertTrue(first.result(timeout=10)['ok'])
        self.assertEqual(len(calls), 1)

    def test_checkpoint_owner_process_crash_releases_the_persistent_inode(self):
        lock = self.root / '.protection.lock'
        code = ('import sys; from romeo_mcp.checkpoint_storage import protection_lock; '
                'owner=protection_lock(sys.argv[1]); owner.__enter__(); '
                'print("ready",flush=True); sys.stdin.readline()')
        child = subprocess.Popen([sys.executable, '-c', code, str(lock)],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True, cwd=Path(__file__).resolve().parents[1])
        try:
            self.assertEqual(child.stdout.readline().strip(), 'ready')
            inode = lock.stat().st_ino
            with self.assertRaises(OSError):
                with checkpoint_storage.protection_lock(lock):
                    self.fail('active owner ignored')
            child.kill()
            child.wait(timeout=10)
            # Windows may finish kernel handle reclamation just after wait().
            # This is an OS release delay, not a persisted application TTL.
            import time
            deadline = time.monotonic() + 2
            while True:
                try:
                    with checkpoint_storage.protection_lock(lock):
                        self.assertEqual(lock.stat().st_ino, inode)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(.01)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=10)
            for stream in (child.stdin, child.stdout, child.stderr):
                stream.close()


@unittest.skipUnless(os.name == 'posix', 'remote helpers need POSIX descriptors and /proc')
class CrossToolConflicts(unittest.TestCase):
    def setUp(self):
        Reservations.setUp(self)
        self.roots = [str(self.root), '/tmp']

    def stop(self, child):
        if child.stdin and not child.stdin.closed:
            child.stdin.close()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.terminate()
            child.wait(timeout=5)
        for stream in (child.stdout, child.stderr):
            stream.close()

    def supervise(self, path, direction='upload', recursive=False, basename='payload'):
        import select
        request = dict(path=str(path), roots=self.roots, direction=direction, basename=basename,
                       recursive=recursive, verify=True, lock_root=str(self.cache))
        child = subprocess.Popen([sys.executable, '-u', '-c', confined_transfers.SUPERVISOR, json.dumps(request)],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True, encoding='utf-8')
        self.addCleanup(self.stop, child)
        self.assertTrue(select.select([child.stdout], [], [], 10)[0], 'supervisor did not reply')
        return child, json.loads(child.stdout.readline())

    def write(self, path, content='new', action='replace'):
        request = dict(path=str(path), roots=self.roots, content=base64.b64encode(content.encode()).decode(),
                       action=action, expected=None, lock_root=str(self.cache))
        response = subprocess.run([sys.executable, '-c', file_operations._WRITE, json.dumps(request)],
                                  capture_output=True, text=True, encoding='utf-8', timeout=10)
        self.assertEqual(response.returncode, 0, response.stderr)
        return json.loads(response.stdout)

    def test_upload_refuses_other_upload_download_and_file_replace_but_allows_sibling(self):
        owner, ready = self.supervise(self.target)
        self.assertTrue(ready['ok'], ready)
        for direction in ('upload', 'download'):
            _, reply = self.supervise(self.target, direction)
            self.assertFalse(reply['ok'], reply)
            self.assertIn('Conflit', reply['error'])
        self.assertFalse(self.write(self.target)['ok'])
        self.assertTrue(self.write(self.root / 'sibling', action='create')['ok'])
        self.assertEqual(self.target.read_text(), 'original')

    def test_downloads_share_source_but_writer_is_refused_until_both_finish(self):
        readers = [self.supervise(self.target, 'download') for _ in range(2)]
        self.assertTrue(all(ready['ok'] for _, ready in readers))
        self.assertFalse(self.write(self.target)['ok'])
        self.stop(readers[0][0])
        self.assertFalse(self.write(self.target)['ok'])
        self.stop(readers[1][0])
        self.assertTrue(self.write(self.target)['ok'])

    def test_recursive_upload_blocks_descendants_and_aliases_but_not_siblings(self):
        tree = self.root / 'tree'
        tree.mkdir()
        (tree / 'child').write_text('original')
        alias = self.root / 'alias'
        alias.symlink_to(tree, target_is_directory=True)
        self.roots.append(str(alias))
        _, ready = self.supervise(self.root, recursive=True, basename='tree')
        self.assertTrue(ready['ok'], ready)
        for path in (tree / 'child', alias / 'child'):
            self.assertFalse(self.write(path)['ok'])
            _, reader = self.supervise(path, 'download')
            self.assertFalse(reader['ok'], reader)
        self.assertTrue(self.write(self.root / 'other', action='create')['ok'])
        self.assertEqual((tree / 'child').read_text(), 'original')

    def test_upload_checksum_mismatch_never_replaces_original_and_cleans_stage(self):
        child, ready = self.supervise(self.target)
        self.assertTrue(ready['ok'], ready)
        Path(ready['proxy']).write_text('corrupted')
        child.stdin.write(json.dumps({'action': 'commit', 'expected_sha256': '0' * 64}) + '\n')
        child.stdin.flush()
        reply = json.loads(child.stdout.readline())
        self.assertFalse(reply['ok'], reply)
        self.stop(child)
        self.assertEqual(self.target.read_text(), 'original')
        self.assertEqual(list(self.root.glob('.romeo-transfer-*')), [])

    def test_file_creation_has_exactly_one_winner_across_twelve_processes(self):
        target = self.root / 'created'
        with ThreadPoolExecutor(12) as pool:
            responses = list(pool.map(lambda n: self.write(target, str(n), 'create'), range(12)))
        winners = [str(n) for n, reply in enumerate(responses) if reply['ok']]
        self.assertEqual(len(winners), 1, responses)
        self.assertEqual(target.read_text(), winners[0])


class Admission(unittest.IsolatedAsyncioTestCase):
    async def test_real_stdio_rpc_cancellation_keeps_running_worker_admitted(self):
        from mcp import ClientSession, StdioServerParameters, stdio_client
        with tempfile.TemporaryDirectory(prefix='romeo-rpc-cancellation-') as temporary:
            root = Path(temporary)
            launcher = root / 'server.py'
            launcher.write_text(
                'import asyncio,json,time\nfrom pathlib import Path\n'
                'from romeo_mcp.profiles import ProfiledServer\n'
                'root=Path(' + repr(str(root)) + ')\n'
                'server=ProfiledServer(name="isolated-cancelled-rpc")\nserver.max_active_calls=1\n'
                'def controlled(number:int)->dict:\n'
                ' (root/"ready").write_text("ready")\n'
                ' deadline=time.monotonic()+10\n'
                ' while not (root/"release").exists():\n'
                '  if time.monotonic()>deadline: raise RuntimeError("test deadline")\n'
                '  time.sleep(.01)\n'
                ' (root/"finished").write_text("finished")\n'
                ' return {"ok":True,"number":number}\n'
                'server.add_tool(controlled)\nasyncio.run(server.run_stdio_async())\n', encoding='utf-8')
            parameters = StdioServerParameters(command=sys.executable, args=[str(launcher)],
                env={**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1]), 'ROMEO_UPDATE_CHECK': '0'})
            async with stdio_client(parameters) as (read, write), ClientSession(read, write) as client:
                await client.initialize()
                request = asyncio.create_task(client.call_tool('controlled', {'number': 1}))
                try:
                    async def wait_file(name):
                        while not (root/name).exists():
                            await asyncio.sleep(.01)
                    await asyncio.wait_for(wait_file('ready'), 10)
                    request.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await request
                    response = await client.call_tool('controlled', {'number': 2})
                    self.assertTrue(response.is_error, response)
                    self.assertFalse(json.loads(response.content[0].text)['execution_started'])
                finally:
                    (root/'release').write_text('release')
                await asyncio.wait_for(wait_file('finished'), 10)
                third = await client.call_tool('controlled', {'number': 3})
                self.assertFalse(third.is_error, third)
                self.assertEqual(json.loads(third.content[0].text)['number'], 3)

    async def test_profile_change_keeps_its_own_result_while_notification_is_pending(self):
        from types import SimpleNamespace
        from romeo_mcp import outils_accompagnement as discovery
        entered, release = asyncio.Event(), asyncio.Event()
        async def notify():
            entered.set()
            await release.wait()
        server = ProfiledServer(name='isolated-profile-change')
        context = SimpleNamespace(session=SimpleNamespace(send_tool_list_changed=notify))
        with patch.object(discovery, 'server', server):
            first = asyncio.create_task(discovery.tool_profile_set('expert', context))
            try:
                await asyncio.wait_for(entered.wait(), timeout=10)
                other = await discovery.tool_profile_set('essential')
                self.assertFalse(other['ok'], other)
                self.assertEqual(server.tool_profile, 'expert')
            finally:
                release.set()
            self.assertEqual((await first)['profile'], 'expert')
            self.assertTrue((await discovery.tool_profile_set('essential'))['ok'])

    async def test_flood_has_a_bounded_queue_and_refusals_never_run_the_tool(self):
        entered, release = threading.Event(), threading.Event()
        calls, lock = [], threading.Lock()
        def controlled(number: int) -> dict:
            with lock:
                calls.append(number)
                if len(calls) >= 32:
                    entered.set()
            release.wait(10)
            return {'ok': True}
        server = ProfiledServer(name='isolated-admission-flood')
        server.add_tool(controlled)
        requests = [asyncio.create_task(server.call_tool('controlled', {'number': n})) for n in range(120)]
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait, 10))
            self.assertEqual(server._active_calls, 48)
            refusals = [r.result() for r in requests if r.done()]
            self.assertEqual(len(refusals), 72)
            self.assertTrue(all(r.is_error and not json.loads(r.content[0].text)['execution_started'] for r in refusals))
        finally:
            release.set()
            responses = await asyncio.gather(*requests)
        self.assertEqual(len(calls), 48)
        self.assertEqual(sum(bool(r.is_error) for r in responses), 72)
        self.assertEqual(server._active_calls, 0)

    async def test_cancelled_rpc_keeps_capacity_until_the_real_worker_finishes(self):
        entered, release = threading.Event(), threading.Event()
        calls = []
        def controlled(number: int) -> dict:
            calls.append(number)
            entered.set()
            release.wait(10)
            return {'ok': True}
        server = ProfiledServer(name='isolated-concurrency-test')
        server.max_active_calls = 1
        server.add_tool(controlled)
        request = asyncio.create_task(server.call_tool('controlled', {'number': 1}))
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait, 10))
            request.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await request
            busy = await server.call_tool('controlled', {'number': 2})
            self.assertTrue(busy.is_error)
            self.assertFalse(json.loads(busy.content[0].text)['execution_started'])
            self.assertEqual(calls, [1])
            self.assertEqual(server._active_calls, 1)
        finally:
            release.set()
            await asyncio.gather(*server._running_calls)
        self.assertEqual(server._active_calls, 0)
        await server.call_tool('controlled', {'number': 3})
        self.assertEqual(calls, [1, 3])


if __name__ == '__main__':
    unittest.main(verbosity=2)
