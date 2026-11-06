"""RTK : reecriture sans replay, budget global, garde-fous avant SSH et installation.

Le SSH est simule ici pour couvrir les cas inaccessibles sur ROMEO (login d'une autre
architecture, coupure). Le script lui-meme est eprouve par smoke_rtk_install_live.py.
"""
from __future__ import annotations

import asyncio
from dataclasses import replace
import json
import os
import re
import shlex
import sys
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import offline  # noqa: E402
from romeo_mcp import guard, noyau, outils_execution as execution, rtk, server  # noqa: E402,F401
from romeo_mcp.resource_locks import ResourceBusy  # noqa: E402
from romeo_mcp.ssh import Result, SSHError, SSHTimeout  # noqa: E402


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
        self.assertEqual(result["rtk"]["install"]["state"], "disabled")
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
            self.assertEqual(result["pinned_version"], rtk.PINNED.version)
            self.assertEqual(result["install"]["state"], "disabled")
            remote.assert_called_once()
        with patch.object(execution, "_sh", side_effect=[Result(0, self.binary, 0),
                         Result(0, "rtk 1.0.1", 0)]) as remote:
            result = execution.rtk_status(include_gain=False)
            self.assertTrue(result["ok"])
            self.assertEqual(result["version"], "rtk 1.0.1")
            self.assertEqual(result["pinned_version"], rtk.PINNED.version)
            self.assertNotIn("install", result)
            self.assertEqual(remote.call_count, 2)
        for response in (Result(0, "[]", 0), Result(0, "not json", 0),
                         Result(0, "{}", 0, True), Result(1, "error", 0)):
            with self.subTest(response=response), patch.object(execution, "_sh", side_effect=[
                    Result(0, self.binary, 0), Result(0, "rtk 1.0.1", 0), response]):
                self.assertFalse(execution.rtk_status()["ok"])

    def test_status_may_write_and_stays_additive_in_full_profile(self):
        # L'annotation doit rester exacte : l'installation au premier besoin ecrit sur le compte.
        with patch.object(noyau.server, "tool_profile", "full"):
            tools = {t.name: t for t in asyncio.run(noyau.server.list_tools())}
        self.assertFalse(tools["rtk_status"].annotations.read_only_hint)
        self.assertFalse(tools["rtk_status"].annotations.destructive_hint)
        self.assertNotIn("login_command_run", tools)


class RTKAutoInstallTests(unittest.TestCase):
    def setUp(self):
        self.connection = SimpleNamespace(host="romeo-test", user="user", home="/home/test user",
                                          scratch="/scratch/test", path_aliases=[])
        self.binary = "/home/test user/.local/bin/rtk"
        self.calls = []
        self.present = False
        self.outcome = Result(0, "RTK_INSTALL_DONE\n", 2.0)
        rtk._attempts.clear()
        self.addCleanup(rtk._attempts.clear)
        self.enterContext(patch.dict(os.environ, {"ROMEO_RTK_AUTO_INSTALL": "1"}))
        self.remote_mock = Mock(side_effect=self.remote)
        for target, name, value in ((execution, "session", Mock(return_value=self.connection)),
                                    (execution, "_sh", self.remote_mock),
                                    (rtk, "session", Mock(return_value=self.connection)),
                                    (rtk, "_sh", self.remote_mock)):
            self.enterContext(patch.object(target, name, value))

    def remote(self, _connection, command, **kwargs):
        self.calls.append((command, kwargs))
        if "RTK_INSTALL_DONE" in command:
            if isinstance(self.outcome, Exception):
                raise self.outcome
            self.present = "RTK_INSTALL_DONE" in self.outcome.stdout
            return self.outcome
        if "type -P rtk" in command:
            return Result(0, self.binary, 0) if self.present else Result(127, "", 0)
        if " rewrite -- " in command:
            return Result(3, "rtk git status", 0)
        if command.endswith("--version"):
            return Result(0, "rtk " + rtk.PINNED.version, 0)
        if command.endswith("gain --format json"):
            return Result(0, '{"summary": {}}', 0)
        return Result(0, "sortie", 0)

    def scripts(self):
        return [call for call in self.calls if "RTK_INSTALL_DONE" in call[0]]

    def executed(self):
        return [call[0] for call in self.calls if call[0].endswith(("git status", "hostname"))
                and " rewrite -- " not in call[0]]

    def test_pin_designates_the_official_static_x86_64_archive(self):
        pin = rtk.PINNED
        self.assertTrue(pin.url.startswith("https://github.com/rtk-ai/rtk/releases/download/v{}/".format(pin.version)))
        self.assertEqual(pin.asset, "rtk-oss-x86_64-unknown-linux-musl.tar.gz")
        for digest in (pin.archive_sha256, pin.binary_sha256):
            self.assertRegex(digest, r"\A[0-9a-f]{64}\Z")

    def test_script_binds_the_pin_stays_in_the_home_and_never_overwrites(self):
        script = rtk.install_script("/home/test user")
        for expected in ("archive_sha256=" + rtk.PINNED.archive_sha256, "binary_sha256=" + rtk.PINNED.binary_sha256,
                         "url=" + rtk.PINNED.url, "home='/home/test user'", "--proto '=https'", "--proto-redir '=https'",
                         "curl -q ", "Linux/x86_64", 'ln -T -- "$tmp/rtk" "$target"', "fail 12 present",
                         'mktemp -d -- "$anchor/.rtk-install.XXXXXX"'):
            self.assertIn(expected, script)
        self.assertNotRegex(script, r"rm -rf|mv |/tmp|--insecure|\s-k\s|RTK_SKIP_CHECKSUM|releases/latest|install\.sh")

    def test_first_command_installs_then_runs_through_rtk(self):
        result = execution.login_command_run("git status", use_rtk=True)
        self.assertTrue(result["ok"], result)
        install = result["rtk"]["install"]
        self.assertEqual(install["state"], "installed")
        self.assertTrue(install["attempted_now"])
        self.assertEqual(install["path"], self.binary)
        self.assertEqual(install["version"], "rtk " + rtk.PINNED.version)
        self.assertEqual(install["archive_sha256"], rtk.PINNED.archive_sha256)
        self.assertEqual(result["executed_command"], "rtk git status")
        self.assertEqual(result["rtk"]["path"], self.binary)
        self.assertEqual(result["rtk"]["reason"], "rewritten")
        self.assertEqual(self.scripts()[0][0], rtk.install_script("/home/test user"))
        rtk.session.assert_called_once_with(longue=True)
        again = execution.login_command_run("git status", use_rtk=True)
        self.assertNotIn("install", again["rtk"])
        self.assertEqual(len(self.scripts()), 1)

    def test_installation_does_not_consume_the_command_budget(self):
        clock = SimpleNamespace(now=100.0)
        def remote(connection, command, **kwargs):
            if "RTK_INSTALL_DONE" in command:
                clock.now += 30
            return self.remote(connection, command, **kwargs)
        with patch.object(rtk, "time", SimpleNamespace(monotonic=lambda: clock.now)), \
                patch.object(rtk, "_sh", side_effect=remote):
            result = execution.login_command_run("git status", use_rtk=True, timeout_seconds=10)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["rtk"]["install"]["duration_seconds"], 30)
        self.assertEqual(self.calls[-1][1]["timeout"], 10)

    def test_status_installs_at_first_need_and_reads_the_new_binary(self):
        result = execution.rtk_status()
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["available"])
        self.assertEqual(result["path"], self.binary)
        self.assertEqual(result["version"], "rtk " + rtk.PINNED.version)
        self.assertEqual(result["install"]["state"], "installed")
        self.assertEqual(result["gain"], {"summary": {}})
        self.assertNotIn("install", execution.rtk_status())
        self.assertEqual(len(self.scripts()), 1)

    def test_present_binary_is_used_and_nothing_is_installed(self):
        self.present = True
        self.assertNotIn("install", execution.rtk_status())
        self.assertNotIn("install", execution.login_command_run("git status", use_rtk=True)["rtk"])
        self.assertEqual(self.scripts(), [])

    def test_opt_out_never_installs_and_keeps_the_raw_command(self):
        for value in ("0", "false", "no", "FALSE", "No"):
            with self.subTest(value=value), patch.dict(os.environ, {"ROMEO_RTK_AUTO_INSTALL": value}):
                result = execution.login_command_run("git status", use_rtk=True)
                self.assertTrue(result["ok"])
                self.assertEqual(result["executed_command"], "git status")
                self.assertEqual(result["rtk"]["reason"], "not_installed")
                self.assertEqual(result["rtk"]["install"]["state"], "disabled")
                self.assertEqual(execution.rtk_status()["install"]["state"], "disabled")
        self.assertEqual(self.scripts(), [])
        self.assertEqual(rtk._attempts, {})

    def test_raw_mode_and_refused_commands_never_install(self):
        self.assertTrue(execution.login_command_run("git status")["ok"])
        refused = execution.login_command_run("make -j8", use_rtk=True)
        self.assertTrue(refused["refused"])
        self.assertEqual(self.scripts(), [])

    def test_known_failure_keeps_the_command_raw_reports_it_and_never_retries(self):
        for code, needle in ((10, "x86_64"), (11, "sort du home"), (12, "n'est pas remplace"), (13, "Telechargement"),
                             (14, "differe de l'epingle"), (15, "binaire different"), (16, "Ecriture"), (18, "Outil absent")):
            with self.subTest(code=code):
                rtk._attempts.clear()
                self.calls.clear()
                self.outcome = Result(code, "RTK_INSTALL_FAILED cause {}\n".format(code), 1)
                result = execution.login_command_run("git status", use_rtk=True)
                self.assertTrue(result["ok"])
                self.assertEqual(result["executed_command"], "git status")
                self.assertEqual(result["rtk"]["reason"], "not_installed")
                install = result["rtk"]["install"]
                self.assertEqual(install["state"], "failed")
                self.assertIn(needle, install["error"])
                self.assertEqual(install["exit_code"], code)
                self.assertEqual(install["detail"], "cause {}".format(code))
                self.assertEqual(install["execution_outcome"], "failed")
                self.assertTrue(install["attempted_now"])
                self.assertIn("prochain demarrage", install["next_step"])
                self.assertEqual(self.executed(), ["git status"])
                again = execution.login_command_run("git status", use_rtk=True)
                self.assertFalse(again["rtk"]["install"]["attempted_now"])
                status = execution.rtk_status()
                self.assertTrue(status["ok"])
                self.assertFalse(status["available"])
                self.assertEqual(status["install"]["exit_code"], code)
                self.assertFalse(status["install"]["attempted_now"])
                self.assertEqual(len(self.scripts()), 1)

    def test_unknown_outcomes_keep_the_command_raw_without_replay(self):
        for outcome in (SSHTimeout("delai"), SSHError("coupure"), Result(17, "RTK_INSTALL_FAILED version\n", 1),
                        Result(0, "sans marqueur", 1), Result(129, "", 1)):
            with self.subTest(outcome=outcome):
                rtk._attempts.clear()
                self.calls.clear()
                self.outcome = outcome
                result = execution.login_command_run("git status", use_rtk=True)
                self.assertTrue(result["ok"])
                self.assertEqual(result["executed_command"], "git status")
                self.assertEqual(result["rtk"]["install"]["state"], "failed")
                self.assertEqual(result["rtk"]["install"]["execution_outcome"], "unknown")
                self.assertFalse(execution.login_command_run("git status", use_rtk=True)["rtk"]["install"]["attempted_now"])
                self.assertEqual(len(self.scripts()), 1)

    def test_other_account_gets_its_own_attempt(self):
        self.outcome = Result(13, "RTK_INSTALL_FAILED curl 7\n", 1)
        execution.login_command_run("git status", use_rtk=True)
        other = SimpleNamespace(**{**vars(self.connection), "user": "autre"})
        self.assertTrue(rtk.provision(other)["attempted_now"])
        self.assertEqual(len(self.scripts()), 2)

    def test_concurrent_install_leaves_the_command_raw_and_can_try_later(self):
        with rtk._attempts_lock:
            result = execution.login_command_run("git status", use_rtk=True)
        self.assertEqual(result["executed_command"], "git status")
        self.assertEqual(result["rtk"]["install"]["state"], "in_progress")
        self.assertEqual(self.scripts(), [])
        with patch.object(rtk, "ResourceLease", side_effect=ResourceBusy("occupe")):
            result = execution.login_command_run("git status", use_rtk=True)
        self.assertEqual(result["rtk"]["install"]["state"], "in_progress")
        self.assertEqual(rtk._attempts, {})
        self.assertEqual(execution.login_command_run("git status", use_rtk=True)["rtk"]["install"]["state"], "installed")

    def test_parallel_first_needs_attempt_only_once(self):
        entered, release = threading.Event(), threading.Event()
        def remote(connection, command, **kwargs):
            if "RTK_INSTALL_DONE" in command:
                entered.set()
                release.wait(5)
            return self.remote(connection, command, **kwargs)
        results = []
        with patch.object(rtk, "_sh", side_effect=remote):
            first = threading.Thread(target=lambda: results.append(rtk.provision(self.connection)))
            first.start()
            self.assertTrue(entered.wait(5))
            self.assertEqual(rtk.provision(self.connection)["state"], "in_progress")
            release.set()
            first.join(5)
        self.assertEqual(results[0]["state"], "installed")
        self.assertEqual(len(self.scripts()), 1)

    def test_local_failures_never_stop_the_command(self):
        for error in (ValueError("registre"), OSError("disque")):
            with self.subTest(error=error), patch.object(rtk, "ResourceLease", side_effect=error):
                rtk._attempts.clear()
                result = execution.login_command_run("git status", use_rtk=True)
                self.assertTrue(result["ok"])
                self.assertEqual(result["rtk"]["install"]["state"], "failed")
        class Unreadable:
            host, home = "romeo-test", "/home/test user"

            @property
            def user(self):
                raise SSHError("coupure")
        self.assertEqual(rtk.provision(Unreadable())["state"], "failed")

    def test_invalid_binary_after_installation_is_reported_with_its_state(self):
        def remote(connection, command, **kwargs):
            if command.endswith("--version"):
                self.calls.append((command, kwargs))
                return Result(0, "autre chose", 0)
            return self.remote(connection, command, **kwargs)
        with patch.object(execution, "_sh", side_effect=remote):
            result = execution.rtk_status()
        self.assertFalse(result["ok"])
        self.assertEqual(result["install"]["state"], "installed")

    def test_starting_the_server_installs_nothing(self):
        async def names():
            return {tool.name for tool in await noyau.server.list_tools()}
        with patch.object(noyau.server, "tool_profile", "expert"):
            tools = asyncio.run(names())
        self.assertIn("rtk_status", tools)
        self.assertFalse({"rtk_install", "rtk_install_prepare"} & tools)
        self.assertEqual(self.calls, [])
        rtk.session.assert_not_called()

    def test_altered_release_is_carried_into_the_script(self):
        altered = replace(rtk.PINNED, archive_sha256="0" * 64)
        self.assertIn("archive_sha256=" + "0" * 64, rtk.install_script("/home/test user", altered))
        self.assertNotIn(rtk.PINNED.archive_sha256, rtk.install_script("/home/test user", altered))

    def test_server_instructions_describe_the_automatic_installation(self):
        text = re.sub(r"\s+", " ", noyau.INSTRUCTIONS)
        self.assertIn("ne l'installe pas a la main", text)
        self.assertIn("ROMEO_RTK_AUTO_INSTALL=0", text)


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
