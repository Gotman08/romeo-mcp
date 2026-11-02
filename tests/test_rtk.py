"""RTK : reecriture sans replay, budget global et garde-fous avant SSH."""
from __future__ import annotations

import asyncio
import json
import shlex
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import offline  # noqa: E402
from romeo_mcp import guard, noyau, outils_execution as execution, rtk, server  # noqa: E402,F401
from romeo_mcp.ssh import Result, SSHTimeout  # noqa: E402


class RTKTests(unittest.TestCase):
    def setUp(self):
        self.connection = SimpleNamespace(home="/home/test user", scratch="/scratch/test", path_aliases=[])
        self.binary = "/home/test user/.local/bin/rtk"
        self.enterContext(patch.object(execution, "session", return_value=self.connection))

    def test_raw_mode_preserves_command_and_exit_without_probe(self):
        with patch.object(execution, "_sh", return_value=Result(42, "failure", 0.3)) as remote:
            result = execution.login_command_run("git status", max_chars=800)
        self.assertFalse(result["ok"])
        self.assertEqual(result["exit_code"], 42)
        self.assertEqual(result["duration_seconds"], 0.3)
        remote.assert_called_once()
        self.assertEqual(remote.call_args.args[1], "git status")
        self.assertEqual(remote.call_args.kwargs["max_chars"], 800)

    def test_both_rewrite_exit_codes_execute_once_in_same_cwd(self):
        for rc in (0, 3):
            responses = [Result(0, self.binary + "\n", 0), Result(rc, "rtk git status", 0),
                         Result(17, "filtered failure", 0, True)]
            with self.subTest(rc=rc), patch.object(execution, "_sh", side_effect=responses) as remote:
                result = execution.login_command_run("git status", use_rtk=True, cwd="project")
                self.assertEqual(result["exit_code"], 17)
                self.assertTrue(result["truncated"])
                self.assertTrue(result["rtk"]["applied"])
                self.assertEqual(result["executed_command"], "rtk git status")
                self.assertEqual(remote.call_count, 3)
                for call in remote.call_args_list:
                    self.assertEqual(call.kwargs["cwd"], "/scratch/test/project")
                self.assertIn(shlex.quote(self.binary), remote.call_args_list[1].args[1])
                self.assertTrue(remote.call_args.args[1].endswith("\nrtk git status"))
                self.assertIn("RTK_TELEMETRY_DISABLED=1", remote.call_args.args[1])

    def test_missing_rtk_falls_back_once_and_discloses_it(self):
        with patch.object(execution, "_sh", side_effect=[Result(127, "", 0), Result(0, "raw", 0)]) as remote:
            result = execution.login_command_run("git status", use_rtk=True)
        self.assertTrue(result["ok"])
        self.assertEqual(result["rtk"]["reason"], "not_installed")
        self.assertEqual(remote.call_count, 2)
        self.assertEqual(remote.call_args.args[1], "git status")

    def test_unmapped_command_runs_unchanged_once(self):
        with patch.object(execution, "_sh", side_effect=[Result(0, self.binary, 0),
                         Result(1, "", 0), Result(0, "node", 0)]) as remote:
            result = execution.login_command_run("hostname", use_rtk=True)
        self.assertTrue(result["ok"])
        self.assertEqual(result["rtk"]["reason"], "not_rewritten")
        self.assertEqual(remote.call_args.args[1], "hostname")

    def test_refused_original_and_invalid_limits_never_probe_or_execute(self):
        for kwargs in ({"command": "make -j8"}, {"command": "rtk cargo test"},
                       {"command": "pwd", "max_chars": 64001}, {"command": "pwd", "max_chars": True},
                       {"command": "pwd", "max_chars": 0}, {"command": "pwd", "timeout_seconds": True}):
            with self.subTest(kwargs=kwargs), patch.object(execution, "_sh") as remote, \
                    patch.object(execution, "session") as connect:
                result = execution.login_command_run(**kwargs, use_rtk=True)
                self.assertFalse(result["ok"])
                self.assertTrue(result["refused"])
                remote.assert_not_called()
                connect.assert_not_called()

    def test_rewritten_command_is_checked_again(self):
        with patch.object(execution, "_sh", side_effect=[Result(0, self.binary, 0),
                         Result(3, "rtk cargo test", 0)]) as remote:
            result = execution.login_command_run("git status", use_rtk=True)
        self.assertFalse(result["ok"])
        self.assertTrue(result["refused"])
        self.assertEqual(remote.call_count, 2)

    def test_denied_broken_or_truncated_rewrite_never_executes_original(self):
        for response in (Result(2, "", 0), Result(2, "blocked", 0), Result(7, "error", 0),
                         Result(1, "unexpected output", 0), Result(3, "", 0),
                         Result(3, "rtk git status", 0, True)):
            with self.subTest(response=response), patch.object(execution, "_sh", side_effect=[
                    Result(0, self.binary, 0), response]) as remote:
                result = execution.login_command_run("git status", use_rtk=True)
                self.assertFalse(result["ok"])
                self.assertEqual(remote.call_count, 2)

    def test_budget_counts_probe_and_rewrite_before_execution(self):
        with patch.object(rtk, "time", SimpleNamespace(monotonic=Mock(side_effect=[0, 1, 4, 8]))), \
                patch.object(execution, "_sh", side_effect=[Result(0, self.binary, 0),
                             Result(3, "rtk git status", 0), Result(0, "ok", 0)]) as remote:
            result = execution.login_command_run("git status", use_rtk=True, timeout_seconds=10)
        self.assertTrue(result["ok"], result)
        self.assertEqual([c.kwargs["timeout"] for c in remote.call_args_list], [9, 6, 2])

    def test_expired_budget_and_ssh_timeout_do_not_trigger_raw_replay(self):
        with patch.object(rtk, "time", SimpleNamespace(monotonic=Mock(side_effect=[0, 1, 4, 11]))), \
                patch.object(execution, "_sh", side_effect=[Result(0, self.binary, 0),
                             Result(3, "rtk git status", 0)]) as remote:
            self.assertFalse(execution.login_command_run("git status", use_rtk=True, timeout_seconds=10)["ok"])
            self.assertEqual(remote.call_count, 2)
        with patch.object(execution, "_sh", side_effect=[Result(0, self.binary, 0),
                         Result(3, "rtk git status", 0), SSHTimeout("timeout")]) as remote:
            self.assertFalse(execution.login_command_run("git status", use_rtk=True)["ok"])
            self.assertEqual(remote.call_count, 3)

    def test_discovery_rejects_incomplete_or_multiline_path(self):
        for response in (Result(0, self.binary, 0, True), Result(0, "rtk", 0),
                         Result(0, self.binary + "\nextra", 0), Result(1, "probe failed", 0)):
            with self.subTest(response=response), patch.object(execution, "_sh", return_value=response) as remote:
                self.assertFalse(execution.login_command_run("pwd", use_rtk=True)["ok"])
                self.assertEqual(remote.call_count, 1)

    def test_status_returns_version_and_json_statistics(self):
        stats = {"total_commands": 4, "tokens_saved": 42}
        with patch.object(execution, "_sh", side_effect=[Result(0, self.binary, 0),
                         Result(0, "rtk 1.0.1\n", 0), Result(0, json.dumps(stats), 0)]) as remote:
            result = execution.rtk_status()
        self.assertTrue(result["available"])
        self.assertEqual(result["gain"], stats)
        self.assertIn("gain --format json", remote.call_args.args[1])

    def test_status_without_gain_missing_and_invalid_json(self):
        with patch.object(execution, "_sh", return_value=Result(127, "", 0)) as remote:
            result = execution.rtk_status()
            self.assertTrue(result["ok"])
            self.assertFalse(result["available"])
            remote.assert_called_once()
        with patch.object(execution, "_sh", side_effect=[Result(0, self.binary, 0),
                         Result(0, "rtk 1.0.1", 0)]) as remote:
            self.assertTrue(execution.rtk_status(include_gain=False)["ok"])
            self.assertEqual(remote.call_count, 2)
        for response in (Result(0, "[]", 0), Result(0, "not json", 0),
                         Result(0, "{}", 0, True), Result(1, "error", 0)):
            with self.subTest(response=response), patch.object(execution, "_sh", side_effect=[
                    Result(0, self.binary, 0), Result(0, "rtk 1.0.1", 0), response]):
                self.assertFalse(execution.rtk_status()["ok"])

    def test_status_is_read_only_and_available_in_full_profile(self):
        with patch.object(noyau.server, "tool_profile", "full"):
            tools = {t.name: t for t in asyncio.run(noyau.server.list_tools())}
        self.assertTrue(tools["rtk_status"].annotations.read_only_hint)
        self.assertNotIn("login_command_run", tools)


class RTKGuardTests(unittest.TestCase):
    def test_rtk_cannot_hide_heavy_destructive_or_opaque_commands(self):
        for command in ("rtk cargo test", "/home/user/.local/bin/rtk -vv cargo build",
                        "rtk --skip-env pip install numpy", "rtk bypass make -j8", "rtk bypass -- make -j8",
                        "rtk bypass 'make -j8'", "rtk bypass -- 'make -j8'", "rtk run --shell 'make -j8'",
                        "rtk test 'cargo test'", "rtk find . -exec make ';'"):
            with self.subTest(command=command), self.assertRaises(guard.GuardError):
                guard.check_login_command(command)
        for command in ("rtk bypass rm -rf /", "rtk bypass -- rm -rf /", "rtk bypass bash -c 'rm -rf /'"):
            with self.subTest(command=command), self.assertRaises(guard.GuardError):
                guard.check_login_command(command, allow_heavy=True)

    def test_supported_inspection_and_literal_args_are_preserved(self):
        for command in ("rtk git status", "rtk git log -3", "rtk ls -la", "rtk read file.txt",
                        "rtk rg 'make -j8' file.txt", "rtk gain --format json",
                        "rtk --version", "rtk bypass hostname", "rtk git status && rtk ls"):
            with self.subTest(command=command):
                guard.check_login_command(command)
        guard.check_login_command("rtk cargo test", allow_heavy=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
