"""Dashboard isolation, historical evidence, bounded inputs and optional launch."""
from __future__ import annotations

import hashlib
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from romeo_mcp import terminal, terminal_data as data, terminal_evidence as evidence, updates
from romeo_mcp.issue_store import ReportStore
from romeo_mcp.transfer_progress import ProgressLog, command, parse
from romeo_mcp.registry import _SCHEMA


class TerminalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="romeo terminal ")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / "local data/jobs.db"
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("ROMEO_")}
        self.env.update(ROMEO_CONFIG=str(self.root / "config.json"), ROMEO_MCP_DB=str(self.db),
                        ROMEO_UPDATES_DIR=str(self.root / "updates"), ROMEO_UPDATE_CHECK="0",
                        PYTHONIOENCODING="utf-8", PYTHONPATH=str(ROOT))
        self.environment = patch.dict(os.environ, self.env, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def create_job(self, *, observation=None, state="SUBMITTED", with_observations=True):
        self.db.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.db)) as connection:
            connection.executescript(_SCHEMA)
            connection.execute("INSERT INTO jobs(job_id,name,submitted_at,partition,script,last_state) "
                               "VALUES (?,?,?,?,?,?)", ("101", "Simulation", time.time() - 600, "cpu",
                                                       "private-command-do-not-export", state))
            if observation is not None:
                connection.execute("INSERT INTO job_observations VALUES (?,?,?,?)",
                                   ("101", '{"host":"private-target"}', time.time() - 180, json.dumps(observation)))
            if not with_observations:
                connection.execute("DROP TABLE job_observations")
            connection.commit()

    def cli(self, *args):
        return subprocess.run([sys.executable, "-m", "romeo_mcp", *args],
                              cwd=self.root, env=self.env, input="", text=True,
                              encoding="utf-8", capture_output=True, timeout=15)

    def test_empty_snapshot_creates_no_configuration_database_or_update_files(self):
        result = data.snapshot()
        self.assertEqual(result["schema"], 2)
        self.assertEqual(result["jobs"], [])
        self.assertFalse(result["runtime"]["registry_present"])
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertNotIn("romeo_mcp.server", sys.modules)
        self.assertNotIn("romeo_mcp.ssh", sys.modules)

    def test_demo_is_synthetic_and_never_reads_private_files(self):
        with patch.object(data, "registry_path", side_effect=AssertionError("private read")), \
                patch.object(data, "read_json", side_effect=AssertionError("private read")), \
                patch.object(data, "reports", side_effect=AssertionError("private report read")):
            result = data.snapshot(demo=True)
        self.assertTrue(result["demo"])
        self.assertEqual(len(result["jobs"]), 4)
        self.assertFalse(result["jobs"][2]["result_validated"])
        self.assertTrue(result["transfers"][1]["result_validated"])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_completed_is_historical_and_does_not_validate_results_or_export_private_context(self):
        self.create_job(observation={"ok": True, "job_id": "101", "state": "COMPLETED",
                                    "elapsed": "00:02:00", "exit_code": "0:0", "result_validated": False})
        before = self.db.read_bytes()
        result = data.snapshot()
        job = result["jobs"][0]
        self.assertEqual(job["state"], "COMPLETED")
        self.assertFalse(job["result_validated"])
        self.assertGreater(time.time() - job["observed_at"], 179)
        serialized = json.dumps(result)
        self.assertNotIn("private-target", serialized)
        self.assertNotIn("private-command", serialized)
        self.assertEqual(self.db.read_bytes(), before)

    def test_other_job_observation_is_not_displayed_as_evidence(self):
        self.create_job(observation={"ok": True, "job_id": "999", "state": "COMPLETED", "result_validated": True})
        result = data.snapshot()
        self.assertEqual(result["jobs"][0]["state"], "SUBMITTED")
        self.assertIsNone(result["jobs"][0]["observed_at"])
        self.assertFalse(result["jobs"][0]["result_validated"])
        self.assertTrue(result["warnings"])

    def test_service_readiness_does_not_replace_the_slurm_job_observation(self):
        self.create_job(observation={"ok": True, "job_id": "101", "state": "RUNNING"}, state="RUNNING")
        with closing(sqlite3.connect(self.db)) as connection:
            connection.execute("INSERT INTO job_observations VALUES (?,?,?,?)", (
                "101", '{"host":"service-target"}', time.time(),
                json.dumps({"ok": True, "job_id": "101", "service_id": "service", "state": "ready"})))
            connection.commit()
        job = data.snapshot()["jobs"][0]
        self.assertEqual(job["state"], "RUNNING")
        self.assertGreater(time.time() - job["observed_at"], 179)

    def test_job_named_service_id_is_not_mistaken_for_a_service_observation(self):
        self.create_job(observation={"ok": True, "job_id": "101", "name": "service_id", "state": "RUNNING"})
        job = data.snapshot()["jobs"][0]
        self.assertEqual(job["state"], "RUNNING")
        self.assertIsNotNone(job["observed_at"])

    def test_old_registry_and_corrupt_database_do_not_break_the_dashboard(self):
        self.create_job(with_observations=False)
        self.assertIsNone(data.snapshot()["jobs"][0]["observed_at"])
        self.db.write_bytes(b"invalid database")
        result = data.snapshot()
        self.assertEqual(result["jobs"], [])
        self.assertTrue(result["warnings"])

    def test_oversized_observation_is_bounded_and_ignored(self):
        self.create_job(observation={"ok": True, "job_id": "101", "state": "RUNNING",
                                    "padding": "x" * (data.MAX_OBSERVATION + 1)})
        result = data.snapshot()
        self.assertEqual(result["jobs"][0]["state"], "SUBMITTED")
        self.assertLess(len(json.dumps(result)), 3000)
        self.assertTrue(result["warnings"])

    def test_transfer_identity_and_plan_integrity_are_checked_without_running_a_worker(self):
        directory = self.db.parent / "transfers" / ("c" * 32)
        directory.mkdir(parents=True)
        plan = {"id": directory.name, "direction": "download", "local_path": "result.dat",
                "remote_path": "simulation/result.dat", "recursive": False, "verify": True,
                "target": {"host": "private-target"}, "created_at": time.time() - 60}
        plan["sha256"] = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
        (directory / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        status = {"transfer_id": directory.name, "state": "completed", "ok": True,
                  "result_validated": True, "heartbeat_at": time.time() - 20}
        (directory / "status.json").write_text(json.dumps(status), encoding="utf-8")
        result = data.snapshot()
        self.assertTrue(result["transfers"][0]["result_validated"])
        self.assertNotIn("private-target", json.dumps(result))
        plan["local_path"] = "changed.dat"
        (directory / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        self.assertEqual(data.snapshot()["transfers"], [])

    def test_cached_updates_are_read_without_network_lock_files_or_policy_writes(self):
        target = updates.installation()
        target.root.mkdir(parents=True)
        (target.root / "check.json").write_text(json.dumps({"schema": 2, "checked_at": time.time() - 900,
                    "release": {"version": "9.0.0"}, "error": None}), encoding="utf-8")
        before = {str(path.relative_to(self.root)): path.read_bytes()
                  for path in self.root.rglob("*") if path.is_file()}
        with patch.object(updates, "latest_release", side_effect=AssertionError("network")):
            result = data.snapshot()
        self.assertEqual(result["updates"]["latest_version"], "9.0.0")
        self.assertTrue(result["updates"]["update_available"])
        after = {str(path.relative_to(self.root)): path.read_bytes()
                 for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(before, after)

    def test_checkpoint_is_bound_to_the_job_and_keeps_runtime_age(self):
        self.create_job(observation={"ok": True, "job_id": "101", "state": "TIMEOUT"})
        runtime = {"schema": "romeo-runtime-observation-v1", "job_id": "101", "run_id": "example",
                   "world_size": 8, "binding_sha256": "a" * 64, "observed_at": time.time() - 3600,
                   "binding": {"private-program": "private-inputs"}, "resume_validated": True,
                   "checkpoint_after_signal_verified": True,
                   "latest_checkpoint": {"run_id": "example", "world_size": 8, "binding_sha256": "a" * 64,
                                         "manifest_sha256": "b" * 64, "generation": 7, "step": 1200,
                                         "integrity_verified": True, "directory": "private-checkpoint-path"}}
        def save():
            with closing(sqlite3.connect(self.db)) as db:
                db.execute("DELETE FROM job_observations WHERE job_id='checkpoint:101'")
                db.execute("INSERT INTO job_observations VALUES (?,?,?,?)",
                           ("checkpoint:101", "{}", time.time(), json.dumps(runtime)))
                db.commit()
        save()
        before = self.db.read_bytes()
        result = data.snapshot()
        checkpoint = result["jobs"][0]["checkpoint"]
        self.assertEqual(checkpoint["step"], 1200)
        self.assertTrue(checkpoint["integrity_verified"])
        self.assertTrue(checkpoint["resume_validated"])
        self.assertGreater(time.time() - checkpoint["observed_at"], 3599)
        self.assertNotIn("private-", json.dumps(checkpoint))
        self.assertEqual(before, self.db.read_bytes())
        runtime["latest_checkpoint"]["binding_sha256"] = "c" * 64
        save()
        result = data.snapshot()
        self.assertIsNone(result["jobs"][0]["checkpoint"])
        self.assertEqual(result["jobs"][0]["state"], "TIMEOUT")
        self.assertTrue(result["warnings"])
        runtime["world_size"] = 1
        runtime["latest_checkpoint"].update(binding_sha256="a" * 64, world_size=True)
        with self.assertRaises(ValueError):
            evidence.checkpoint(json.dumps(runtime), "101")

    def test_progress_requires_transport_evidence_not_a_heartbeat(self):
        self.assertIsNone(evidence.progress({"heartbeat_at": time.time(), "elapsed_seconds": 99}))
        observed = {"bytes_transferred": 48, "bytes_total": 120, "observed_at": time.time() - 90}
        self.assertEqual(evidence.progress({"progress": observed})["bytes_total"], 120)
        for change in ({"bytes_total": 0}, {"bytes_total": 12}, {"bytes_total": True},
                       {"bytes_transferred": True}, {"observed_at": float("nan")}):
            self.assertIsNone(evidence.progress({"progress": {**observed, **change}}))
        reported = {**observed, "source": "rsync_progress2", "bytes_total": None, "percent_reported": 40}
        result = evidence.progress({"progress": reported})
        self.assertIsNone(result["bytes_total"])
        self.assertEqual(result["percent_reported"], 40)
        self.assertEqual(result["observed_at"], observed["observed_at"])
        for change in ({"source": "clock"}, {"percent_reported": 101}, {"percent_reported": True}):
            self.assertIsNone(evidence.progress({"progress": {**reported, **change}}))

    def test_reports_are_read_only_and_export_no_body_credentials_or_foreign_url(self):
        store = ReportStore()
        store.configure(True)
        record = store.save({"schema": 1, "repository": updates.REPOSITORY, "summary": "Exemple fictif",
                             "category": "bug", "observed": "private-body-not-for-dashboard"})
        store.update(record["report_id"], "published", issue_number=41,
                     issue_url=f"https://github.com/{updates.REPOSITORY}/issues/41")
        before = store.path.read_bytes()
        with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("HTTP")), \
                patch.object(store.__class__, "update", side_effect=AssertionError("write")):
            result = data.snapshot()["reports"]
        self.assertEqual(before, store.path.read_bytes())
        self.assertTrue(result["automatic_enabled"])
        self.assertTrue(result["items"][0]["result_validated"])
        self.assertEqual(result["items"][0]["issue_number"], 41)
        self.assertNotIn("private-body", json.dumps(result))
        store.update(record["report_id"], "failed", issue_number=41,
                     issue_url="https://foreign.invalid/secret-query")
        result = data.snapshot()["reports"]["items"][0]
        self.assertEqual(result["issue_url"], "")
        self.assertIsNone(result["issue_number"])
        self.assertFalse(result["result_validated"])
        with patch.dict(os.environ, ROMEO_AUTO_ISSUES="0"):
            self.assertFalse(data.snapshot()["reports"]["automatic_enabled"])
        self.assertTrue(store.policy()["saved_automatic"])

    def test_corrupt_reports_do_not_prevent_jobs_from_being_read(self):
        self.create_job()
        store = ReportStore()
        store.root.mkdir()
        store.path.write_bytes(b"invalid reports database")
        result = data.snapshot()
        self.assertEqual(result["jobs"][0]["id"], "101")
        self.assertEqual(result["reports"], {"automatic_enabled": None, "items": []})
        self.assertTrue(result["warnings"])

    def test_controls_large_numbers_and_oversized_local_json_are_safe(self):
        self.assertNotIn("\x1b", data.text("name\x1b[31m\n\u202e"))
        self.assertNotIn("\u202e", data.text("name\x1b[31m\n\u202e"))
        self.assertIsNone(data.timestamp(10 ** 400))
        self.assertIsNone(data.timestamp(True))
        self.assertIsNone(data.timestamp(float("nan")))
        file = self.root / "large.json"
        file.write_bytes(b" " * (data.MAX_JSON + 1))
        with self.assertRaises(ValueError):
            data.read_json(file)

    def test_bridge_supports_multiple_requests_and_eof_without_mcp_stdout(self):
        code = "import sys; sys.path.insert(0, sys.argv.pop(1)); from romeo_mcp.terminal_data import bridge; bridge()"
        result = subprocess.run([sys.executable, "-I", "-u", "-c", code, str(ROOT), "--demo"],
                                input="snapshot\nsnapshot\n", capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 2)
        self.assertTrue(all(json.loads(line)["demo"] for line in result.stdout.splitlines()))

    def test_cli_json_and_noninteractive_rejection_do_not_require_cargo(self):
        demo = self.cli("tui", "--demo", "--json")
        self.assertEqual(demo.returncode, 0, demo.stderr)
        self.assertTrue(json.loads(demo.stdout)["demo"])
        redirected = self.cli("tui", "--demo")
        self.assertEqual(redirected.returncode, 1)
        self.assertIn("terminal interactif", redirected.stderr)
        self.assertEqual(redirected.stdout, "")
        for args in (("--limit", "0"), ("--refresh", "999"), ("--width", "10000")):
            self.assertNotEqual(self.cli("tui", "--json", *args).returncode, 0)

    def test_launch_preserves_argument_boundaries_for_paths_with_spaces(self):
        binary = self.root / "custom viewer.exe"
        binary.write_text("fixture", encoding="utf-8")
        args = SimpleNamespace(refresh=5, limit=40, width=100, height=30, json=False, snapshot=True,
                               build=False, binary=str(binary), view="jobs", demo=True, db=self.db)
        with patch.object(terminal.subprocess, "run", return_value=SimpleNamespace(returncode=7)) as launch:
            self.assertEqual(terminal.run(args), 7)
        command = launch.call_args.args[0]
        self.assertEqual(command[0], str(binary))
        self.assertEqual(command[command.index("--db") + 1], str(self.db))
        self.assertEqual(command[command.index("--python") + 1], sys.executable)
        self.assertNotIn("shell", launch.call_args.kwargs)


class ProgressTests(unittest.TestCase):
    def test_rsync_parser_keeps_reported_percentage_and_distinguishes_elapsed_time(self):
        line = b" 50331648 40% 4.00MB/s 0:00:18  "
        result = parse(line, 100.0)
        self.assertEqual(result["bytes_transferred"], 50331648)
        self.assertEqual(result["bytes_per_second"], 4 * 1024 ** 2)
        self.assertEqual(result["eta_seconds"], 18)
        self.assertIsNone(result["bytes_total"])
        end = parse(b" 125829120 100% 4.00MB/s 0:00:30 (xfr#1, to-chk=0/1)", 101.0)
        self.assertIsNone(end["eta_seconds"])
        for bad in (b"secret-name 40%", b"48 101% 4.00MB/s 0:00:18", b"48 40% 4.00MB/s 0:99:00",
                    b"48 40% 4.00MB/s 0:00:18 (xfr#1, ir-chk=0/1)", b"48 40% nanMB/s 0:00:18"):
            self.assertIsNone(parse(bad, 100.0))

    def test_tail_is_bounded_complete_and_does_not_invent_new_measurements(self):
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "transfer.log"
            observer = ProgressLog(log)
            log.write_bytes(b"private-log\n\r48 40% 4.00MB/s 0:00:")
            self.assertIsNone(observer.sample())
            with log.open("ab") as stream:
                stream.write(b"18\r")
            measured = observer.sample()
            self.assertEqual(measured["percent_reported"], 40)
            self.assertIsNone(observer.sample())
            with log.open("ab") as stream:
                stream.write(b"x" * 20000 + b"\n125 100% 4.00MB/s 0:00:30 (xfr#1, to-chk=0/1)\n")
            self.assertEqual(observer.sample()["percent_reported"], 100)
            self.assertLessEqual(len(observer.pending), 512)

    def test_old_rsync_and_other_transports_are_left_usable(self):
        argv = ["rsync", "-az", "--partial", "source with spaces", "target"]
        for version, enabled in ((b"rsync version 2.6.9", False), (b"rsync version 3.2.7", True)):
            with patch("romeo_mcp.transfer_progress.subprocess.run",
                       return_value=SimpleNamespace(returncode=0, stdout=version)) as run:
                result, measured = command(argv, {})
            self.assertEqual(measured, enabled)
            self.assertEqual(result[-2:], argv[-2:])
            self.assertNotIn("shell", run.call_args.kwargs)
        with patch("romeo_mcp.transfer_progress.subprocess.run", side_effect=AssertionError("spawn")):
            self.assertEqual(command(["scp", "-q", "source", "target"], {}),
                             (["scp", "-q", "source", "target"], False))


if __name__ == "__main__":
    unittest.main(verbosity=2)
