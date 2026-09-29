"""Contrats des profils, du doctor en lecture seule et des fiches privees."""

import asyncio
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mcp import ClientSession, StdioServerParameters, stdio_client
from romeo_mcp import config, doctor, privacy, reproducibility as repro
from romeo_mcp.profiles import ESSENTIAL_TOOLS
from romeo_mcp.registry import Registry
from romeo_mcp.ssh import Result, SSHError, SSHTimeout


class FakeDoctor:
    def __init__(self, outputs=None, **kwargs):
        self.outputs = outputs or {}
        self.commands = []
        self.closed = False

    def run(self, command, **kwargs):
        self.commands.append(command)
        key = "ssh" if command == "id -un" else "assoc" if command.startswith("sacctmgr") else "partitions" if command.startswith("sinfo") else "project" if "-g " in command else "quota"
        default = {"ssh": "student\n", "assoc": "test-project||normal|normal|\n",
                   "partitions": "instant*|up|01:00:00|4\n",
                   "quota": "gpfs home USR 1G 15G 20G 0 none 20 100 200\n",
                   "project": "gpfs project GRP 2G 30G 40G 0 none 20 100 200\n"}
        result = self.outputs.get(key, Result(0, default[key], 0.01))
        if isinstance(result, Exception):
            raise result
        return result

    def close(self):
        self.closed = True


class DoctorTests(unittest.TestCase):
    def run_doctor(self, overrides=None):
        fake = FakeDoctor(overrides)
        with patch.dict(os.environ, ROMEO_ACCOUNT="test-project", ROMEO_HOST="example-host"):
            result = doctor.live_checks(session_factory=lambda **_: fake)
        self.assertTrue(fake.closed)
        self.assertTrue(all(c.startswith(("id -un", "sacctmgr -nP show assoc", "sinfo -h", "mmlsquota")) for c in fake.commands))
        return result, fake

    def test_healthy_reads_every_required_check(self):
        result, fake = self.run_doctor()
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["checks"]), 5)
        self.assertEqual(len(fake.commands), 5)

    def test_ssh_authentication_failure_stops_reads(self):
        result, fake = self.run_doctor({"ssh": SSHError("Permission denied (publickey)")})
        self.assertFalse(result["ok"])
        self.assertEqual(len(fake.commands), 1)
        self.assertEqual(result["checks"][0]["code"], "ssh_authentication")
        self.assertEqual(sum(c["status"] == "skipped" for c in result["checks"]), 4)

    def test_missing_project_and_empty_success_are_not_healthy(self):
        for data in ("", "another-project||normal|normal|\n"):
            result, _ = self.run_doctor({"assoc": Result(0, data, 0)})
            self.assertFalse(result["ok"])
            self.assertEqual(result["checks"][1]["code"], "association_missing")
        result, _ = self.run_doctor({"quota": Result(0, "", 0)})
        self.assertFalse(result["ok"])

    def test_timeout_truncation_and_partial_failure_are_explicit(self):
        for failure in (SSHTimeout("slow"), Result(1, "private diagnostic", 0), Result(0, "gpfs x", 0, truncated=True)):
            result, fake = self.run_doctor({"quota": failure})
            self.assertFalse(result["ok"])
            self.assertEqual(len(fake.commands), 5)
            self.assertNotIn("private diagnostic", json.dumps(result))

    def test_expired_grace_is_a_warning(self):
        result, _ = self.run_doctor({"quota": Result(0, "gpfs home USR 18G 15G 20G 0 expired", 0)})
        self.assertFalse(result["ok"])
        self.assertEqual(result["checks"][3]["status"], "warning")

    def test_inode_grace_is_reported(self):
        result, _ = self.run_doctor({"quota": Result(0, "gpfs home USR 1G 15G 20G 0 none | 150 100 200 0 expired", 0)})
        self.assertEqual(result["checks"][3]["status"], "warning")
        self.assertEqual(result["checks"][3]["quotas"][0]["files_used"], "150")
        result, _ = self.run_doctor({"quota": Result(0, "gpfs home USR 1G 15G 20G 0 none | 20 100 200 0 none", 0)})
        self.assertTrue(result["ok"])


class ProfileTests(unittest.TestCase):
    def test_configuration_preserves_existing_access(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, ROMEO_CONFIG=str(Path(temp) / "config.json")):
            config.save({"ROMEO_ACCOUNT": "test-project", "ROMEO_HOST": "example-host"})
            config.save({"ROMEO_TOOL_PROFILE": "essential"})
            self.assertEqual(config.load()["ROMEO_ACCOUNT"], "test-project")
            with self.assertRaises(ValueError):
                config.save({"ROMEO_TOOL_PROFILE": "invalid"})

    def test_stdio_profiles_switch_and_notify_without_losing_advanced_tools(self):
        async def exercise():
            env = {**os.environ, "ROMEO_TOOL_PROFILE": "full", "ROMEO_ACCOUNT": "test-project",
                   "ROMEO_HOST": "invalid-offline-host", "PYTHONIOENCODING": "utf-8", "PYTHONPATH": str(ROOT)}
            received = []
            async def handle(message):
                received.append(str(message))
            params = StdioServerParameters(command=sys.executable, args=["-m", "romeo_mcp", "serve", "--profile", "essential"], env=env)
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write, message_handler=handle) as client:
                    init = await client.initialize()
                    self.assertTrue(init.capabilities.tools.list_changed)
                    essential = (await client.list_tools()).tools
                    self.assertEqual({t.name for t in essential}, ESSENTIAL_TOOLS)
                    current = await client.call_tool("tool_profile_get", {})
                    profile = json.loads(current.content[0].text)
                    self.assertEqual(profile["profile"], "essential")
                    self.assertEqual(set(profile["tools"]), ESSENTIAL_TOOLS)
                    self.assertFalse(any("list_changed" in m for m in received))
                    schema = next(t for t in essential if t.name == "tool_profile_set").input_schema
                    self.assertNotIn("ctx", schema.get("properties", {}))
                    missing = await client.call_tool("tool_profile_set", {})
                    self.assertTrue(missing.is_error)
                    changed = await client.call_tool("tool_profile_set", {"profile": "full"})
                    content = json.loads(changed.content[0].text)
                    self.assertTrue(content["client_notified"], content)
                    full = (await client.list_tools()).tools
                    self.assertGreater(len(full), len(essential) + 20)
                    self.assertIn("python_wheel_prepare", {t.name for t in full})
                    self.assertNotIn("compute_command_prepare", {t.name for t in full})
                    self.assertGreater(len(json.dumps([t.model_dump() for t in full])), len(json.dumps([t.model_dump() for t in essential])))
                    rejected = await client.call_tool("tool_profile_set", {"profile": "invalid"})
                    self.assertTrue(rejected.is_error)
                    self.assertEqual(len((await client.list_tools()).tools), len(full))
                    await client.call_tool("tool_profile_set", {"profile": "expert"})
                    expert = {t.name for t in (await client.list_tools()).tools}
                    self.assertEqual(expert - {t.name for t in full},
                                     {"compute_command_prepare", "compute_command_run", "login_command_run"})
                    await client.call_tool("tool_profile_set", {"profile": "essential"})
                    self.assertEqual({t.name for t in (await client.list_tools()).tools}, ESSENTIAL_TOOLS)
                    self.assertTrue(any("list_changed" in m for m in received))
        asyncio.run(exercise())


class ReproducibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="romeo proof ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Registry(self.root / "jobs.db")
        self.addCleanup(self.store.close)

    def record(self, script="#!/bin/bash\nprintf hello\n", provenance=None):
        self.store.record("123", "example", "instant", "x64cpu", "/scratch_p/student/example",
                          "out", "err", script, provenance=provenance)

    def test_old_database_upgrades_without_changing_existing_job(self):
        old = self.root / "old.db"
        con = sqlite3.connect(old)
        con.execute("CREATE TABLE jobs (job_id TEXT PRIMARY KEY, name TEXT, submitted_at REAL, partition TEXT, arch TEXT, workdir TEXT, stdout_glob TEXT, stderr_glob TEXT, script TEXT, last_state TEXT, note TEXT)")
        con.execute("INSERT INTO jobs (job_id, name, script) VALUES ('456', 'old', 'hostname')")
        con.commit()
        con.close()
        upgraded = Registry(old)
        self.addCleanup(upgraded.close)
        self.assertEqual(upgraded.get("456")["script"], "hostname")
        self.assertIsNone(upgraded.get_provenance("456"))

    def test_replacing_a_job_cannot_keep_obsolete_provenance(self):
        self.record(provenance={"phase": "old"})
        self.record()
        self.assertIsNone(self.store.get_provenance("123"))
        with self.assertRaises(TypeError):
            self.record(script="invalid change", provenance={"bad": object()})
        self.assertNotEqual(self.store.get("123")["script"], "invalid change")

    def test_live_array_export_has_runtime_and_accounting_without_extra_fields(self):
        self.record(provenance={"phase": "before_submission"})
        runtime = {"job_id": "123_7", "phase": "before_workload", "observed_at": "2026-01-01T00:00:00Z",
                   "git": {"status": "observed", "commit": "a" * 40},
                   "data": [{"path": "/scratch_p/student/input.txt", "status": "hashed", "sha256": "b" * 64, "bytes": 4}],
                   "environment": {"architecture": "x86_64", "loaded_modules": ["python/3.11"],
                                   "unexpected": "never-export-extra-field"}, "unexpected": "never-export-extra-field"}

        class Connection:
            home, scratch, path_aliases, user = "/home/user", "/scratch_p/student", [], "student"

            def run(self, command, **kwargs):
                if command.startswith("head -c 24001 -- "):
                    if "printf '\\n'" not in command:
                        raise AssertionError("La lecture doit isoler son marqueur SSH")
                    return Result(0, json.dumps(runtime), 0)
                if command.startswith("timeout 25s python3"):
                    return Result(0, '{"git":{"status":"unavailable"},"data":[]}', 0)
                if command.startswith("sacct -nP -j 123_7 -o JobID,"):
                    tail = "|COMPLETED|00:00:01|00:00:01|1|1G|1200K|cpu=1,mem=1G|0:0|submit|start|end|\n"
                    return Result(0, "123_7|student" + tail + "123_7.batch|" + tail +
                                  "123_8|student" + tail + "123_7|another-user" + tail, 0)
                raise AssertionError(command)

        result = repro.export_report("123_7", output_dir=str(self.root / "reports"), job_registry=self.store, connection=Connection())
        report = json.loads(Path(result["files"]["report.json"]).read_text())
        self.assertEqual(len(report["resource_usage"]), 2)
        self.assertEqual(report["runtime"]["git"]["commit"], "a" * 40)
        self.assertEqual(result["runtime_data_files_hashed"], 1)
        self.assertEqual(report["missing_information"], [])
        self.assertNotIn("never-export-extra-field", json.dumps(report))
        self.assertNotIn("another-user", json.dumps(report))
        with self.assertRaises(ValueError):
            repro._runtime_observation(runtime, "123_8")
        with self.assertRaises(ValueError):
            repro._observation({"git": {}, "data": ["not a file entry"]})

    def test_submission_keeps_declared_metadata_when_ssh_probe_fails(self):
        from romeo_mcp.slurm import JobSpec, plan_job
        plan = plan_job(JobSpec(name="example", command="hostname", account="test-project", mem_gb=1), "/scratch_p/student")
        with patch.object(repro, "observe_files", side_effect=SSHTimeout("private diagnostic")):
            metadata = repro.submission_provenance(object(), plan)
        self.assertEqual(metadata["code"]["status"], "unavailable")
        self.assertEqual(metadata["requested_resources"]["mem_gb"], 1)
        self.assertNotIn("private diagnostic", json.dumps(metadata))

    def test_export_removes_secrets_from_all_written_files_and_return_value(self):
        hidden = ["NeverPublishThis", "MultilinePrivate", "continued-value", "opaque-private-body",
                  "password-in-url", "signed-query-value", "private-key-body"]
        script = ("#!/bin/bash\nexport API_TOKEN=NeverPublishThis\n"
                  "python task.py --password 'MultilinePrivate\nsecond-line'\n"
                  "export OTHER_SECRET=\\\n  continued-value\n"
                  "cat <<'CONFIG'\nopaque-private-body\nCONFIG\n"
                  "curl https://" + "user:password-in-url@example.org/data\n"
                  "curl 'https://example.org/a?X-Amz-Signature=signed-query-value'\n"
                  "-----BEGIN " + "PRIVATE KEY-----\nprivate-key-body\n-----END PRIVATE KEY-----\n"
                  "python science.py --samples 10\n")
        self.record(script, {"environment": {"modules": ["python/3.11"], "API_KEY": "NeverPublishThis"}})
        result = repro.export_report("123", output_dir=str(self.root / "reports"), live=False, job_registry=self.store)
        contents = "\n".join(Path(p).read_text() for p in result["files"].values()) + json.dumps(result)
        for secret in hidden:
            self.assertNotIn(secret, contents)
        self.assertIn("python science.py --samples 10", contents)
        report = json.loads(Path(result["files"]["report.json"]).read_text())
        self.assertTrue(report["script"]["redacted"])
        self.assertEqual(hashlib.sha256(report["script"]["content"].encode()).hexdigest(), report["script"]["exported_sha256"])
        self.assertEqual(self.store.get("123")["script"], script)

    def test_export_refuses_git_destination_invalid_job_and_sensitive_data(self):
        self.record()
        repo = self.root / "repository"
        (repo / ".git").mkdir(parents=True)
        with self.assertRaises(ValueError):
            repro.export_report("123", output_dir=str(repo / "reports"), live=False, job_registry=self.store)
        for jid in ("123; touch bad", "123\n", "../123"):
            with self.assertRaises(ValueError):
                repro.export_report(jid, live=False, job_registry=self.store)
        with self.assertRaises(ValueError):
            repro.export_report("123", data_files=["/home/user/.ssh/id_ed25519"], live=False, job_registry=self.store)
        with self.assertRaises(ValueError):
            repro.export_report("999", live=False, job_registry=self.store)

    def test_probe_hashes_exact_bytes_and_reports_limits(self):
        data = self.root / "input data.txt"
        data.write_bytes(b"scientific input\n")
        outside = self.root.parent / "outside-not-authorized"
        args = {"roots": [str(self.root)], "code_dir": str(self.root),
                "data_files": [str(data), str(outside), str(self.root)], "max_bytes": 64}
        proc = subprocess.run([sys.executable, "-c", repro._PROBE, json.dumps(args)], capture_output=True, text=True, timeout=15)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["data"][0]["sha256"], hashlib.sha256(data.read_bytes()).hexdigest())
        self.assertEqual(result["data"][1]["status"], "unreadable_or_outside_roots")
        self.assertEqual(result["data"][2]["status"], "not_regular_file")
        args["max_bytes"] = 1
        proc = subprocess.run([sys.executable, "-c", repro._PROBE, json.dumps(args)], capture_output=True, text=True, timeout=15)
        self.assertEqual(json.loads(proc.stdout)["data"][0]["status"], "size_limit")

    def test_runtime_capture_is_private_and_does_not_dump_environment(self):
        data = self.root / "input.txt"
        data.write_text("science")
        args = {"roots": [str(self.root)], "code_dir": str(self.root), "data_files": [str(data)], "max_bytes": 64}
        env = {**os.environ, "SLURM_JOB_ID": "123", "LOADEDMODULES": "python/3.11",
               "API_TOKEN": "NeverPublishThis", "SPACK_LOADED_HASHES": "abcdef123"}
        program = repro._PROBE.replace("print(json.dumps(out))", "") + repro._CAPTURE
        proc = subprocess.run([sys.executable, "-c", program, json.dumps(args)], cwd=self.root, env=env,
                              capture_output=True, text=True, timeout=15)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        target = self.root / ".romeo-provenance" / "123.json"
        original = target.read_bytes()
        self.assertTrue(original.endswith(b"\n"))
        self.assertNotIn(b"NeverPublishThis", original)
        record = json.loads(original)
        self.assertEqual(record["phase"], "before_workload")
        self.assertEqual(record["environment"]["loaded_modules"], ["python/3.11"])
        self.assertEqual(record["data"][0]["status"], "hashed")
        if os.name != "nt":
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        subprocess.run([sys.executable, "-c", program, json.dumps(args)], cwd=self.root, env=env, check=True, timeout=15)
        self.assertEqual(target.read_bytes(), original)


if __name__ == "__main__":
    unittest.main(verbosity=2)
