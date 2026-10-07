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
from romeo_mcp import terminal, terminal_data as data, updates
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
        self.assertEqual(result["schema"], 1)
        self.assertEqual(result["jobs"], [])
        self.assertFalse(result["runtime"]["registry_present"])
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertNotIn("romeo_mcp.server", sys.modules)
        self.assertNotIn("romeo_mcp.ssh", sys.modules)

    def test_demo_is_synthetic_and_never_reads_private_files(self):
        with patch.object(data, "registry_path", side_effect=AssertionError("private read")), \
                patch.object(data, "read_json", side_effect=AssertionError("private read")):
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
