"""Transport ambiguity, cache freshness and operations surviving reconnection."""
import asyncio
import json
import os
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
                self.assertTrue((directory / "transfer.log").exists())
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
