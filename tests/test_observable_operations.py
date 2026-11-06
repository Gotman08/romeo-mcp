"""Transport ambiguity, cache freshness and operations surviving reconnection."""
import asyncio
import json
import os
import shlex
import shutil
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import offline
from romeo_mcp import server as assembled
from romeo_mcp import outils_calcul as jobs, outils_contexte as context, outils_diagnostics as diagnostics
from romeo_mcp import transfers, transfer_worker, outils_donnees as data, files, noyau, services
from romeo_mcp import confined_transfers, transfer_progress
from romeo_mcp.observability import ReadCache
from romeo_mcp.registry import Registry
from romeo_mcp.ssh import RomeoSession, Result, SSHError
from romeo_mcp.job_observation import status_command


class ObservableTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="romeo-observed-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.store = Registry(self.root / "jobs.db")
        self.addCleanup(self.store.close)
        self.connection = SimpleNamespace(host="offline-host", user="test-user", home="/home/test",
                                          scratch="/scratch/test-user", path_aliases=[])
        for module in (jobs, diagnostics, transfers):
            mocker = patch.object(module, "registry", return_value=self.store)
            mocker.start()
            self.addCleanup(mocker.stop)
        for module in (jobs, context, transfers, transfer_worker):
            mocker = patch.object(module, "session", return_value=self.connection)
            mocker.start()
            self.addCleanup(mocker.stop)
        mocker = patch.object(data, "session", return_value=self.connection)
        mocker.start()
        self.addCleanup(mocker.stop)

    def test_job_observation_survives_restart_and_is_not_a_current_state(self):
        reply = Result(0, "###LIVE\n12|test|short|RUNNING|1:00|5:00|1|node-1\n###START\n", 0)
        with patch.object(jobs, "_sh", return_value=reply):
            response = jobs.job_status("12")
        self.assertTrue(response["ok"], response)
        self.assertFalse(response["result_validated"])
        with patch.object(jobs, "_sh", side_effect=SSHError("disconnected")):
            failed = jobs.job_status("12")
        self.assertFalse(failed["ok"])
        self.assertEqual(failed["last_observation"]["result"]["state"], "RUNNING")
        self.assertFalse(failed["current_state_observed"])
        local = diagnostics.job_observation_get("12")
        self.assertFalse(local["current_state_observed"])
        reopened = Registry(self.store.path)
        try:
            self.assertEqual(reopened.observation("12")["result"]["state"], "RUNNING")
        finally:
            reopened.close()

    def test_completed_scheduler_job_never_certifies_scientific_result(self):
        reply = Result(0, "###LIVE\n###START\n###PAST\n12|test|short|COMPLETED|1:00|0:0|start|end|\n", 0)
        with patch.object(jobs, "_sh", return_value=reply):
            result = jobs.job_status("12")
        self.assertTrue(result["finished"])
        self.assertTrue(result["scheduler_completed"])
        self.assertFalse(result["result_validated"])

    def test_array_children_are_saved_when_accounting_has_no_parent(self):
        self.store.record("12","array","cpu","x64cpu","/scratch/test-user","out","err","#SBATCH --array=0-2")
        reply = Result(0,"###LIVE\n###PAST\n12_0|array|cpu|COMPLETED|1:00|0:0|start|end|\n12_2|array|cpu|FAILED|1:00|1:0|start|end|\n",0)
        with patch.object(jobs,"_sh",return_value=reply):
            result = jobs.job_status("12")
        self.assertFalse(result["ok"])
        self.assertEqual(self.store.get("12_0")["last_state"],"COMPLETED")
        self.assertEqual(self.store.observation("12_2")["result"]["state"],"FAILED")
        self.assertIsNone(self.store.get("12_1"))

    def test_remaining_dependencies_are_observed_without_an_extra_scheduler_call(self):
        for field,expected in [("afterok:11(unfulfilled)","afterok:11(unfulfilled)"),("(null)","")]:
            reply=Result(0,"###LIVE\n12|test|cpu|PENDING|0:00|5:00|1|Dependency|"+field+"\n",0)
            with patch.object(jobs,"_sh",return_value=reply) as read:
                response=jobs.job_status("12")
            self.assertEqual(response["dependencies_remaining"],expected)
            read.assert_called_once()
            self.assertIn("%E",read.call_args.args[1])

    def test_service_failure_preserves_readiness_without_claiming_it_is_current(self):
        target = {"host": self.connection.host, "user": self.connection.user, "account": "test-project"}
        prepared = self.store.prepare_submission({"kind": "service", "target": target})
        identity = prepared["plan_id"]
        self.store.update_submission(identity, "submitted", {"job_id": "12"})
        with patch.object(services, "registry", return_value=self.store):
            with patch.object(services, "_service", return_value=(self.connection, "12", {})):
                with patch.object(services, "_observe_service", return_value={"ok": True, "job_id": "12", "service_id": identity, "state": "ready"}):
                    ready = services.service_status(identity)
                self.assertTrue(ready["service_readiness_observed"])
                with patch.object(services, "_observe_service", return_value={"ok": False, "job_id": "12", "service_id": identity, "state": "unknown"}):
                    failed = services.service_status(identity)
                self.assertFalse(failed["current_state_observed"])
                self.assertTrue(failed["target_checked"])
                self.assertEqual(failed["last_observation"]["result"]["state"], "ready")
            with patch.object(services, "_service", side_effect=SSHError("identity unavailable")):
                offline_state = services.service_status(identity)
            self.assertFalse(offline_state["target_checked"])
            self.assertFalse(offline_state["current_state_observed"])
            self.assertEqual(offline_state["last_observation"]["result"]["state"], "ready")

    def test_cancel_acceptance_does_not_record_cancelled(self):
        self.store.record("12", "test", "short", "x64cpu", "/scratch/test-user", "out", "err", "script")
        with patch.object(jobs, "_sh", return_value=Result(0, "", 0)):
            result = jobs.cancel_job("12")
        self.assertTrue(result["cancel_requested"])
        self.assertFalse(result["cancellation_observed"])
        self.assertEqual(self.store.get("12")["last_state"], "CANCEL_REQUESTED")

    def test_spack_cache_expires_and_is_scoped_to_identity(self):
        clock = [0.0]
        cache = ReadCache(8, clock=lambda: clock[0])
        with patch.object(context, "_SPACK_CACHE", cache), patch.object(context, "_sh", return_value=Result(0, "python@3.12\nnumpy@2.0", 0)) as remote:
            self.assertFalse(context.romeo_software()["observation"]["cached"])
            self.assertTrue(context.romeo_software(search="numpy")["observation"]["cached"])
            self.assertEqual(remote.call_count, 1)
            clock[0] = 301
            context.romeo_software()
            self.assertEqual(remote.call_count, 2)
            self.connection.user = "another-user"
            context.romeo_software()
            self.assertEqual(remote.call_count, 3)
            context.romeo_software(refresh=True)
            self.assertEqual(remote.call_count, 4)

    def test_truncated_spack_response_is_not_cached(self):
        with patch.object(context, "_SPACK_CACHE", ReadCache()), patch.object(context, "_sh", return_value=Result(0, "python@3.12", 0, truncated=True)) as remote:
            self.assertFalse(context.romeo_software()["ok"])
            self.assertFalse(context.romeo_software()["ok"])
            self.assertEqual(remote.call_count, 2)

    def test_cluster_cache_is_opt_in_and_reports_its_age(self):
        response = Result(0, "###NODES\nn1|idle|x64cpu\n###PART\nshort|up|1:00\n###SHARE\ntest-project|0|1\n###QUEUE\n", 0)
        with patch.object(context, "_STATUS_CACHE", ReadCache()), patch.object(context, "_sh", return_value=response) as remote:
            context.romeo_status()
            context.romeo_status()
            self.assertEqual(remote.call_count, 2)
            cached = context.romeo_status(max_age_seconds=5)
            self.assertTrue(cached["observation"]["cached"])
            self.assertFalse(cached["observation"]["current_state_observed"])
            self.assertEqual(remote.call_count, 2)

    def test_failed_cluster_probe_is_not_an_empty_healthy_cluster(self):
        with patch.object(context, "_sh", return_value=Result(1, "sinfo failed", 0)):
            self.assertFalse(context.romeo_status()["ok"])

    def test_transfer_start_is_single_use_and_status_never_spawns(self):
        source = self.root / "data.txt"
        source.write_text("test")
        prepared = transfers.prepare("upload", str(source), "/scratch/test-user/data.txt")
        identity = prepared["transfer_id"]
        with patch.object(transfers.subprocess, "Popen", return_value=SimpleNamespace(pid=123)) as spawn:
            transfers.start(identity, True)
            repeated = transfers.start(identity, True)
            self.assertTrue(repeated["already_started"])
            self.assertEqual(spawn.call_count, 1)
            self.assertEqual(transfers.status(identity)["liveness"], "unverified")
            cancel = transfers.cancel(identity, True)
            self.assertFalse(cancel["cancellation_observed"])
        self.assertEqual(spawn.call_count, 1)

    def test_corrupt_transfer_plans_are_domain_refusals_and_never_start(self):
        source = self.root/'source.txt'
        source.write_text('fictional')
        identity = transfers.prepare('upload', str(source), '/scratch/test-user/copy')['transfer_id']
        directory, plan = transfers.load(identity)
        faults = [[], None, {}, *[{k: v for k, v in plan.items() if k != missing} for missing in plan]]
        for key, value in [('local_path', ''), ('remote_path', []), ('direction', []),
                           ('recursive', 1), ('verify', None), ('target', []),
                           ('created_at', 'text'), ('created_at', True),
                           ('created_at', 10**400), ('created_at', float('nan'))]:
            bad = {**plan, key: value}
            bad['sha256'] = transfers.seal(bad)
            faults.append(bad)
        with patch.object(transfers.subprocess, 'Popen') as spawn:
            for bad in faults:
                with self.subTest(bad=bad):
                    (directory/'plan.json').write_text(json.dumps(bad))
                    for function in (transfers.status, lambda value: transfers.start(value, True)):
                        with self.assertRaises(ValueError):
                            function(identity)
                    self.assertFalse((directory/'started.claim').exists())
            spawn.assert_not_called()
        transfers.atomic(directory/'plan.json', plan)
        self.assertEqual(transfers.status(identity)['state'], 'prepared')

    def test_corrupt_transfer_states_and_timestamps_are_domain_refusals(self):
        source = self.root/'source.txt'
        source.write_text('fictional')
        identity = transfers.prepare('upload', str(source), '/scratch/test-user/copy')['transfer_id']
        directory, _ = transfers.load(identity)
        base = {'ok': True, 'transfer_id': identity, 'state': 'running', 'result_validated': False}
        faults = [[], None, {}, {**base, 'transfer_id': 'f'*32}, {**base, 'state': []},
                  {**base, 'state': 'unknown'}, {**base, 'ok': 1}, {**base, 'result_validated': []},
                  *[{**base, 'heartbeat_at': value} for value in
                    ('text', [], {}, True, -1, 10**400, float('nan'), float('inf'))]]
        for bad in faults:
            with self.subTest(bad=bad):
                (directory/'status.json').write_text(json.dumps(bad))
                with self.assertRaises(ValueError):
                    transfers.status(identity)
                with self.assertRaises(ValueError):
                    transfers.cancel(identity, True)
                self.assertFalse((directory/'cancel.json').exists())
        (directory/'status.json').write_text('invalid JSON')
        with self.assertRaises(ValueError):
            transfers.status(identity)
        for state in ('launching', 'running', 'completed', 'completed_unverified',
                      'failed', 'cancelled', 'launchFailed'):
            transfers.atomic(directory/'status.json', {**base, 'state': state, 'heartbeat_at': time.time()})
            self.assertEqual(transfers.status(identity)['state'], state)

    def test_empty_local_source_refuses_before_ssh_plan_or_copy(self):
        with patch.object(data, 'session') as connection, patch.object(files, '_run') as copy:
            result = data.upload_to_romeo('', '/scratch/test-user/copy')
            self.assertFalse(result['ok'])
            result = data.download_from_romeo('/scratch/test-user/fictional', '')
            self.assertFalse(result['ok'])
            connection.assert_not_called()
            with self.assertRaises(SSHError):
                files.upload('fictional', '', '/scratch/test-user/copy')
            with self.assertRaises(SSHError):
                files.download('fictional', '/scratch/test-user/fictional', '')
            for direction in ('upload', 'download'):
                with self.assertRaises(ValueError):
                    transfers.prepare(direction, '', '/scratch/test-user/copy')
            copy.assert_not_called()
        self.assertFalse((self.root/'transfers').exists())
        literal = self.root/'file with spaces'
        literal.write_text('fictional')
        selected = Path(transfers.prepare('upload', str(literal), '/scratch/test-user/copy')['plan']['local_path'])
        self.assertTrue(selected.samefile(literal))
        self.assertEqual(selected.name, literal.name)
        if os.name == 'posix':
            trailing = self.root/'file '
            trailing.write_text('fictional')
            selected = Path(transfers.prepare('upload', str(trailing), '/scratch/test-user/copy')['plan']['local_path'])
            self.assertTrue(selected.samefile(trailing))
            self.assertEqual(selected.name, trailing.name)

    def test_cleanup_suggestion_preserves_the_entire_literal_path(self):
        for name in ('cleanup dir;literal', "quote'path", 'literal$(printf TEST)', 'line\npath'):
            path = '/scratch/test-user/' + name
            reply = Result(0, '###LOGS\n1\t' + path.replace('\n', '') + '/old.out\n', 0)
            with patch.object(data, '_sh', return_value=reply):
                result = data.storage_usage_audit(path)
            self.assertTrue(result['ok'], result)
            command = result['suggestions'][0].split(': ', 1)[1]
            argv = shlex.split(command)
            self.assertEqual(argv[0:2], ['find', path])
            self.assertEqual(argv[-1], '-delete')

    def test_transfer_with_unverified_integrity_does_not_claim_verified_completion(self):
        source = self.root / "data.txt"
        source.write_text("test")
        response = transfers.prepare("upload", str(source), "/scratch/test-user/data.txt")
        directory, _ = transfers.load(response["transfer_id"])
        with patch.object(data, "upload_to_romeo") as upload:
            upload.__wrapped__ = Mock(return_value={"ok": True, "verifie": False, "avertissement": "no checksum"})
            self.assertEqual(transfer_worker.run(directory / "plan.json"), 0)
        observed = transfers.status(response["transfer_id"])
        self.assertEqual(observed["state"], "completed_unverified")
        self.assertFalse(observed["result_validated"])

    @unittest.skipUnless(os.name == 'posix', 'vrai superviseur POSIX local ; aucun SSH')
    def test_worker_saves_confined_scp_destination_progress_in_both_directions(self):
        remote = self.root/'remote'
        remote.mkdir()
        self.connection.home = self.connection.scratch = str(remote)
        native_popen = transfer_worker.subprocess.Popen
        copy_program = (
            'import sys,time\n'
            'with open(sys.argv[1],"rb") as source, open(sys.argv[2],"wb") as target:\n'
            ' while True:\n'
            '  block=source.read(65536)\n'
            '  if not block: break\n'
            '  target.write(block); target.flush(); time.sleep(.2)\n'
        )
        launched = []

        def local_process(argv, **kwargs):
            launched.append(argv[0])
            if argv[0] == 'ssh':
                words = shlex.split(argv[-1])
                argv = [sys.executable, '-u', '-c', words[3], words[4]]
            elif argv[0] == 'scp':
                source, destination = argv[-2:]
                prefix = self.connection.host + ':'
                source = source.removeprefix(prefix)
                destination = destination.removeprefix(prefix)
                argv = [sys.executable, '-u', '-c', copy_program, source, destination]
            else:
                self.fail('Processus inattendu dans la copie locale : ' + repr(argv))
            return native_popen(argv, **kwargs)

        for direction, verify in (('upload', True), ('download', True), ('upload', False)):
            with self.subTest(direction=direction, verify=verify):
                source = self.root/'source.bin' if direction == 'upload' else remote/'source.bin'
                destination = remote/'upload.bin' if direction == 'upload' else self.root/'download.bin'
                source.write_bytes(os.urandom(1024 ** 2))
                local = source if direction == 'upload' else destination
                distant = destination if direction == 'upload' else source
                prepared = transfers.prepare(direction, str(local), str(distant), verify=verify)
                directory, _ = transfers.load(prepared['transfer_id'])
                seen = None
                with patch.object(confined_transfers.subprocess, 'Popen', side_effect=local_process):
                    worker = threading.Thread(target=transfer_worker.run, args=(directory/'plan.json',))
                    worker.start()
                    try:
                        deadline = time.monotonic() + 8
                        while worker.is_alive() and time.monotonic() < deadline:
                            observed = transfers.status(prepared['transfer_id'])
                            progress = observed.get('progress') or {}
                            if 0 < progress.get('percent_reported', 100) < 100:
                                seen = observed
                            time.sleep(.02)
                        worker.join(2)
                        self.assertFalse(worker.is_alive())
                    finally:
                        if worker.is_alive():
                            transfers.cancel(prepared['transfer_id'], True)
                            worker.join(5)
                completed = transfers.status(prepared['transfer_id'])
                self.assertIsNotNone(seen, completed)
                self.assertEqual(seen['state'], 'running')
                self.assertFalse(seen['result_validated'])
                self.assertEqual(seen['progress']['source'], 'scp_destination_size')
                self.assertEqual(seen['progress']['bytes_total'], source.stat().st_size)
                self.assertGreater(seen['progress']['bytes_per_second'], 0)
                self.assertGreater(seen['progress']['eta_seconds'], 0)
                self.assertEqual(completed['state'], 'completed' if verify else 'completed_unverified', completed)
                self.assertIs(completed['result_validated'], verify)
                self.assertEqual(completed['result']['transport'], 'scp')
                self.assertEqual(completed['progress']['percent_reported'], 100)
                self.assertEqual(completed['progress']['bytes_transferred'], source.stat().st_size)
                self.assertEqual(completed['progress']['bytes_total'], source.stat().st_size)
                self.assertEqual(source.read_bytes(), destination.read_bytes())
                self.assertIsNone(files._PROGRESS_PROBE.get())
        self.assertEqual(launched, ['ssh', 'scp'] * 3)
        self.assertFalse(list(remote.rglob('.romeo-transfer-*')))
        self.assertFalse(list(self.root.glob('.romeo-download-*')))

    def test_worker_removes_progress_after_a_probe_becomes_invalid(self):
        source = self.root/'source.bin'
        source.write_bytes(b'test')
        prepared = transfers.prepare('upload', str(source), '/scratch/test-user/copy', verify=False)
        directory, _ = transfers.load(prepared['transfer_id'])
        readings = iter([{'valid': True, 'bytes_present': 1, 'bytes_total': 4},
                         {'valid': False, 'bytes_present': None, 'bytes_total': 4}])
        probe = transfer_progress.DestinationProgress(4, lambda: next(readings))

        def copy(*args):
            token = files._PROGRESS_PROBE.set(probe)
            try:
                files._run([sys.executable, '-c', 'import time; time.sleep(2.2)'], 'local bounded probe')
            finally:
                files._PROGRESS_PROBE.reset(token)
            return {'sent': str(source), 'transport': 'scp'}

        with patch.object(files, 'upload', side_effect=copy):
            worker = threading.Thread(target=transfer_worker.run, args=(directory/'plan.json',))
            worker.start()
            seen, removed = False, False
            try:
                deadline = time.monotonic() + 6
                while worker.is_alive() and time.monotonic() < deadline:
                    observed = transfers.status(prepared['transfer_id'])
                    if observed.get('progress'):
                        seen = True
                    elif seen and observed['state'] == 'running':
                        removed = True
                    time.sleep(.02)
                worker.join(2)
                self.assertFalse(worker.is_alive())
            finally:
                if worker.is_alive():
                    transfers.cancel(prepared['transfer_id'], True)
                    worker.join(5)
        completed = transfers.status(prepared['transfer_id'])
        self.assertTrue(seen, completed)
        self.assertTrue(removed, completed)
        self.assertNotIn('progress', completed)
        self.assertEqual(completed['state'], 'completed_unverified', completed)
        self.assertFalse(completed['result_validated'])

    @unittest.skipUnless(shutil.which("rsync"), "rsync facultatif absent ; repli scp conserve")
    def test_worker_saves_real_rsync_progress_without_claiming_integrity(self):
        source, destination = self.root / "source.bin", self.root / "copy.bin"
        source.write_bytes(os.urandom(3 * 1024 ** 2))
        prepared = transfers.prepare("upload", str(source), "/scratch/test-user/copy.bin", verify=False)
        directory, _ = transfers.load(prepared["transfer_id"])
        def copy(*args):
            files._run([shutil.which("rsync"), "-az", "--partial", "--bwlimit=1024",
                        str(source), str(destination)], "local test copy")
            return {"sent": str(source), "bytes": source.stat().st_size, "transport": "rsync"}
        with patch.object(files, "upload", side_effect=copy):
            worker = threading.Thread(target=transfer_worker.run, args=(directory / "plan.json",))
            worker.start()
            seen = None
            try:
                deadline = time.monotonic() + 12
                while worker.is_alive() and time.monotonic() < deadline:
                    observed = transfers.status(prepared["transfer_id"])
                    if observed.get("progress", {}).get("percent_reported", 100) < 100:
                        seen = observed["progress"]
                    time.sleep(0.05)
                worker.join(2)
                self.assertFalse(worker.is_alive())
                self.assertIsNotNone(seen, transfers.status(prepared["transfer_id"]))
                completed = transfers.status(prepared["transfer_id"])
                self.assertEqual(completed["state"], "completed_unverified", completed)
                self.assertFalse(completed["result_validated"])
                self.assertEqual(completed["progress"]["percent_reported"], 100)
                self.assertEqual(completed["progress"]["bytes_transferred"], source.stat().st_size)
                self.assertIsNone(completed["progress"]["bytes_total"])
                self.assertIsNone(completed["progress"]["eta_seconds"])
                self.assertEqual(source.read_bytes(), destination.read_bytes())
            finally:
                if worker.is_alive():
                    transfers.cancel(prepared["transfer_id"], True)
                    worker.join(8)

    def test_progress_parse_accepts_rsync35_and_legacy_records(self):
        # Lignes reelles, rsync 3.5.1 avec --info=progress2 --no-human-readable.
        record = transfer_progress.parse(b"          32768B   1%       0B/s    0:00:00  ", 0.0)
        self.assertEqual((record["bytes_transferred"], record["percent_reported"]), (32768, 1))
        self.assertEqual((record["bytes_per_second"], record["eta_seconds"]), (0, 0))
        record = transfer_progress.parse(b"        3145728B 100% 1055240B/s    0:00:02 (xfr#1, to-chk=0/1)", 0.0)
        self.assertEqual((record["bytes_transferred"], record["percent_reported"]), (3145728, 100))
        self.assertEqual(record["bytes_per_second"], 1055240)
        self.assertIsNone(record["eta_seconds"])
        # Ancien format, compteurs nus et vitesse avec unite : toujours accepte.
        record = transfer_progress.parse(b"        3145728 100%    1.00MB/s    0:00:02 (xfr#1, to-chk=0/1)", 0.0)
        self.assertEqual(record["bytes_per_second"], 1024 ** 2)
        self.assertIsNone(transfer_progress.parse(b"not a progress line", 0.0))

    def test_cancellation_stops_a_real_owned_transfer_process(self):
        source = self.root / "data.txt"
        source.write_text("test")
        response = transfers.prepare("upload", str(source), "/scratch/test-user/data.txt")
        directory, _ = transfers.load(response["transfer_id"])
        (directory / "started.claim").touch()
        def copy(*args):
            files._run([sys.executable, "-u", "-c", "import time; print('started'); time.sleep(30)"], "test copy")
            return {"uploaded": str(source)}
        with patch.object(files, "upload", side_effect=copy):
            worker = threading.Thread(target=transfer_worker.run, args=(directory / "plan.json",))
            worker.start()
            try:
                deadline = time.monotonic() + 3
                while not (directory / "transfer.log").exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue((directory / "transfer.log").exists(), transfers.status(response["transfer_id"]))
                transfers.cancel(response["transfer_id"], True)
                worker.join(5)
                self.assertFalse(worker.is_alive())
                observed = transfers.status(response["transfer_id"])
                self.assertEqual(observed["state"], "cancelled", observed)
                self.assertTrue(observed["partial_output_possible"])
            finally:
                if worker.is_alive():
                    transfers.cancel(response["transfer_id"], True)
                    worker.join(8)

    def test_guidance_only_lists_registered_tool_names(self):
        with patch.object(noyau.server, "tool_profile", "expert"):
            names = {t.name for t in asyncio.run(noyau.server.list_tools())}
            groups = diagnostics.romeo_capabilities()["groups"]
        self.assertTrue(all(t["name"] in names for g in groups for t in g["tools"]))


class DestinationProgressTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'horodatages des fichiers Windows')
    def test_real_windows_file_signature_survives_a_modified_timestamp(self):
        with tempfile.TemporaryDirectory(prefix='romeo-progress-windows-') as temporary:
            path = Path(temporary)/'source'
            path.write_bytes(b'original')
            before = path.lstat()
            os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns + 5_000_000_000))
            current = path.lstat()
            observed = transfer_progress.regular_file_signature(path)
            self.assertEqual(observed[:4], (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns))
            self.assertIsNone(observed[4])
            self.assertEqual(transfer_progress.regular_file_signature(path), observed)

    def test_real_local_source_signature_detects_mtime_and_size_changes(self):
        with tempfile.TemporaryDirectory(prefix='romeo-progress-changed-') as temporary:
            path = Path(temporary)/'source'
            path.write_bytes(b'original')
            original = transfer_progress.regular_file_signature(path)
            os.utime(path, ns=(path.stat().st_atime_ns, original[3] + 5_000_000_000))
            changed_time = transfer_progress.regular_file_signature(path)
            self.assertEqual(changed_time[:3], original[:3])
            self.assertNotEqual(changed_time[3], original[3])
            with path.open('ab') as stream:
                stream.write(b'x')
            os.utime(path, ns=(path.stat().st_atime_ns, original[3]))
            changed_size = transfer_progress.regular_file_signature(path)
            self.assertEqual(changed_size[3], original[3])
            self.assertEqual(changed_size[2], original[2] + 1)
            self.assertNotEqual(changed_size, original)

    def test_destination_bytes_define_percentage_but_not_integrity(self):
        readings = iter([{'valid': True, 'bytes_present': done, 'bytes_total': 100}
                         for done in (0, 40, 100)])
        observer = transfer_progress.DestinationProgress(100, lambda: next(readings))
        with patch.object(transfer_progress.time, 'monotonic', side_effect=[10, 12, 14]), \
                patch.object(transfer_progress.time, 'time', side_effect=[1000, 999, 998]):
            first, middle, final = observer.sample(), observer.sample(), observer.sample()
        self.assertEqual(first['source'], 'scp_destination_size')
        self.assertIsNone(first['bytes_per_second'])
        self.assertIsNone(first['eta_seconds'])
        self.assertEqual(middle['percent_reported'], 40)
        self.assertEqual(middle['bytes_per_second'], 20)
        self.assertEqual(middle['eta_seconds'], 3)
        self.assertEqual(final['percent_reported'], 100)
        self.assertEqual(final['bytes_transferred'], 100)
        self.assertEqual(final['bytes_total'], 100)
        self.assertEqual(final['eta_seconds'], 0)
        self.assertNotIn('result_validated', final)

    def test_pending_measurements_preserve_cached_timestamp_and_rate_baseline(self):
        readings = iter([None, {'valid': True, 'bytes_present': 40, 'bytes_total': 100},
                         None, None, {'valid': True, 'bytes_present': 60, 'bytes_total': 100}])
        observer = transfer_progress.DestinationProgress(100, lambda: next(readings))
        with patch.object(transfer_progress.time, 'monotonic', side_effect=[10, 20]) as measured, \
                patch.object(transfer_progress.time, 'time', side_effect=[1000, 1001]) as dated:
            self.assertIsNone(observer.sample())
            self.assertIsNone(observer.previous)
            first = observer.sample()
            baseline = observer.previous
            pending = observer.sample()
            self.assertEqual(pending, first)
            self.assertIsNot(pending, first)
            self.assertEqual(observer.previous, baseline)
            pending['bytes_transferred'] = 999
            self.assertEqual(observer.sample(), first)
            self.assertEqual(observer.previous, baseline)
            following = observer.sample()
        self.assertEqual(measured.call_count, 2)
        self.assertEqual(dated.call_count, 2)
        self.assertEqual(first['observed_at'], 1000)
        self.assertEqual(following['observed_at'], 1001)
        self.assertEqual(following['bytes_per_second'], 2)
        self.assertEqual(following['eta_seconds'], 20)

    def test_finish_uses_the_fresh_final_callback_instead_of_the_poll_callback(self):
        poll = Mock(return_value={'valid': True, 'bytes_present': 40, 'bytes_total': 100})
        final = Mock(return_value={'valid': True, 'bytes_present': 100, 'bytes_total': 100})
        observer = transfer_progress.DestinationProgress(100, poll, final)
        self.assertEqual(observer.sample()['percent_reported'], 40)
        self.assertEqual(observer.finish()['percent_reported'], 100)
        poll.assert_called_once_with()
        final.assert_called_once_with()

    def test_delayed_replies_and_final_measurement_use_request_times_for_age_and_rate(self):
        readings = iter([{'valid': True, 'bytes_present': 20, 'bytes_total': 100,
                          'observed_at': 1000, 'observed_monotonic': 10},
                         {'valid': True, 'bytes_present': 60, 'bytes_total': 100,
                          'observed_at': 1010, 'observed_monotonic': 20}, None])
        final = Mock(return_value={'valid': True, 'bytes_present': 100, 'bytes_total': 100,
                                   'observed_at': 1020, 'observed_monotonic': 30})
        observer = transfer_progress.DestinationProgress(100, lambda: next(readings), final)
        clock = [1030, 40]
        with patch.object(transfer_progress.time, 'time', side_effect=lambda: clock[0]), \
                patch.object(transfer_progress.time, 'monotonic', side_effect=lambda: clock[1]):
            first = observer.sample()
            clock[:] = [1045, 55]
            middle = observer.sample()
            baseline = observer.previous
            clock[:] = [1050, 60]
            self.assertEqual(observer.sample(), middle)
            self.assertEqual(observer.previous, baseline)
            clock[:] = [1060, 70]
            completed = observer.finish()
        self.assertEqual(first['observed_at'], 1000)
        self.assertEqual(middle['observed_at'], 1010)
        self.assertEqual(middle['bytes_per_second'], 4)
        self.assertEqual(middle['eta_seconds'], 10)
        self.assertEqual(completed['observed_at'], 1020)
        self.assertEqual(completed['bytes_per_second'], 4)
        self.assertEqual(completed['eta_seconds'], 0)
        final.assert_called_once_with()

    def test_inconsistent_or_unavailable_measurements_permanently_remove_the_gauge(self):
        invalid = [{'valid': False},
                   {'valid': True, 'bytes_present': -1, 'bytes_total': 100},
                   {'valid': True, 'bytes_present': 101, 'bytes_total': 100},
                   {'valid': True, 'bytes_present': 20, 'bytes_total': 99},
                   {'valid': True, 'bytes_present': True, 'bytes_total': 100}]
        for bad in invalid:
            with self.subTest(bad=bad):
                readings = iter([{'valid': True, 'bytes_present': 40, 'bytes_total': 100},
                                 bad, {'valid': True, 'bytes_present': 50, 'bytes_total': 100}])
                observer = transfer_progress.DestinationProgress(100, lambda: next(readings))
                self.assertIsNotNone(observer.sample())
                self.assertIsNone(observer.sample())
                self.assertIsNone(observer.sample())
        with self.assertRaises(ValueError):
            transfer_progress.DestinationProgress(0, lambda: self.fail('Aucun total fiable'))

    def test_regressing_destination_size_permanently_removes_the_gauge(self):
        readings = iter([{'valid': True, 'bytes_present': done, 'bytes_total': 100}
                         for done in (40, 20, 50)])
        observer = transfer_progress.DestinationProgress(100, lambda: next(readings))
        self.assertIsNotNone(observer.sample())
        self.assertIsNone(observer.sample())
        self.assertIsNone(observer.sample())

    def test_local_destination_is_zero_until_created_then_latches_inode_replacement(self):
        with tempfile.TemporaryDirectory(prefix='romeo-progress-local-') as temporary:
            path = Path(temporary)/'destination'
            observer = transfer_progress.LocalDestination(path)
            self.assertEqual(observer.sample(), 0)
            path.write_bytes(b'12345678')
            self.assertEqual(observer.sample(), 8)
            path.rename(path.with_name('old-destination'))
            path.write_bytes(b'12345678')
            self.assertIsNone(observer.sample())
            path.write_bytes(b'123456789')
            self.assertIsNone(observer.sample())

    @unittest.skipUnless(os.name == 'posix', 'liens et FIFO POSIX')
    def test_local_destination_refuses_symlink_and_fifo_without_following_or_waiting(self):
        with tempfile.TemporaryDirectory(prefix='romeo-progress-special-') as temporary:
            root = Path(temporary)
            outside = root/'outside'
            outside.write_bytes(b'private')
            for kind in ('symlink', 'fifo'):
                with self.subTest(kind=kind):
                    path = root/kind
                    if kind == 'symlink':
                        path.symlink_to(outside)
                    else:
                        os.mkfifo(path)
                    with self.assertRaises(ValueError):
                        transfer_progress.regular_file_signature(path)
                    self.assertIsNone(transfer_progress.LocalDestination(path).sample())
            self.assertEqual(outside.read_bytes(), b'private')


class TransportTests(unittest.TestCase):
    def test_atomic_replacement_preserves_complete_json_during_sharing_conflict(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "status.json"
            transfers.atomic(path, {"state": "old"})
            replace = os.replace
            calls = []
            def flaky(source, destination):
                calls.append(1)
                if len(calls) == 1:
                    self.assertEqual(transfers.read(path), {"state": "old"})
                    raise PermissionError("reader handle")
                return replace(source, destination)
            with patch.object(transfers.os, "replace", side_effect=flaky):
                transfers.atomic(path, {"state": "new"})
            self.assertEqual(transfers.read(path), {"state": "new"})

    def test_partial_write_never_replays_a_mutation(self):
        connection = RomeoSession("offline-host")
        process = Mock()
        process.stdin.flush.side_effect = BrokenPipeError("partial write")
        with patch.object(connection, "_ensure", return_value=process) as ensure, patch.object(connection, "_reset"):
            with self.assertRaises(SSHError):
                connection.run("sbatch job.sh")
        self.assertEqual(ensure.call_count, 1)
        self.assertEqual(process.stdin.write.call_count, 1)
        self.assertEqual(connection.timings.snapshot()["operations"]["ssh_command"]["failures"], 1)

    def test_explicit_read_can_reconnect_once(self):
        connection = RomeoSession("offline-host")
        with patch.object(connection, "run", side_effect=[SSHError("disconnected"), Result(0, "ok", 0)]) as run:
            self.assertTrue(connection.read("squeue -h").ok)
            self.assertEqual(run.call_count, 2)

    def test_concurrent_identity_reads_are_coalesced_and_reset_clears_cache(self):
        connection = RomeoSession("offline-host")
        with patch.object(connection, "read", return_value=Result(0, "test-user", 0)) as read:
            with ThreadPoolExecutor(max_workers=8) as pool:
                values = list(pool.map(lambda _: connection.user, range(20)))
            self.assertEqual(values, ["test-user"] * 20)
            self.assertEqual(read.call_count, 1)
            connection._reset()
            self.assertEqual(connection.user, "test-user")
            self.assertEqual(read.call_count, 2)


if __name__ == "__main__":
    unittest.main()
