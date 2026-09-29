"""Installation neuve, configuration privee et garde-fous de publication."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from romeo_mcp import config
from tools import check_privacy
from tools import install_mcp


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="romeo setup ")
        self.addCleanup(self.tmp.cleanup)
        self.profile = Path(self.tmp.name) / "private" / "config.json"
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("ROMEO_")}
        self.env.update(ROMEO_CONFIG=str(self.profile), PYTHONPATH=str(ROOT), PYTHONIOENCODING="utf-8")

    def cli(self, *args):
        return subprocess.run([sys.executable, "-m", "romeo_mcp", *args],
                              cwd=self.tmp.name, env=self.env, text=True,
                              encoding="utf-8", capture_output=True, timeout=30)

    def test_clean_install_and_profile_from_unrelated_directory(self):
        missing = self.cli("doctor")
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn("Projet absent", missing.stderr)
        self.assertFalse(json.loads(missing.stdout)["account_configured"])
        invalid = self.cli("configure", "--account", "VOTRE_PROJET")
        self.assertNotEqual(invalid.returncode, 0)
        self.assertFalse(self.profile.exists())
        saved = self.cli("configure", "--account", "test-project")
        self.assertEqual(saved.returncode, 0, saved.stderr)
        self.assertEqual(json.loads(self.profile.read_text())["ROMEO_ACCOUNT"], "test-project")
        result = self.cli("doctor")
        self.assertEqual(result.returncode, 0, result.stderr)
        facts = json.loads(result.stdout)
        self.assertTrue(facts["account_configured"])
        self.assertGreaterEqual(facts["documentation_pages"], 42)
        self.assertFalse(facts["ssh_checked"])
        self.assertNotIn("test-project", result.stdout)

    def test_environment_priority_and_malformed_profile(self):
        with patch.dict(os.environ, self.env, clear=True):
            config.save({"ROMEO_ACCOUNT": "test-project", "ROMEO_HOST": "romeo1"})
            self.assertEqual(config.setting("ROMEO_ACCOUNT"), "test-project")
            with patch.dict(os.environ, ROMEO_ACCOUNT="other-project"):
                self.assertEqual(config.setting("ROMEO_ACCOUNT"), "other-project")
            with patch.dict(os.environ, ROMEO_ACCOUNT=""):
                self.assertEqual(config.setting("ROMEO_ACCOUNT"), "")
            before = self.profile.read_bytes()
            for value in ("project\ncommand", "--help", "project;command"):
                with self.assertRaises(ValueError):
                    config.save({"ROMEO_ACCOUNT": value})
                self.assertEqual(before, self.profile.read_bytes())
            self.profile.write_text('[]', encoding="utf-8")
            with self.assertRaises(ValueError):
                config.load()

    def test_new_client_configuration_is_explicit_and_idempotent(self):
        root = Path(self.tmp.name)
        for client, filename in (("codex", "config.toml"), ("claude-desktop", "client.json")):
            target = root / client / filename
            args = SimpleNamespace(targets=client, codex_config=None, claude_desktop_config=None,
                                   name="romeo", uninstall=False, dry_run=True)
            function = install_mcp.installer_codex if client == "codex" else install_mcp.installer_claude_desktop
            values = ("python", ["-m", "romeo_mcp"], {}, args) if client == "codex" else ({"command": "python", "args": ["-m", "romeo_mcp"]}, args)
            candidates = "candidats_codex" if client == "codex" else "candidats_claude_desktop"
            with patch.object(install_mcp, candidates, return_value=[target]):
                self.assertEqual(function(*values).statut, "simule")
                self.assertFalse(target.exists())
                args.dry_run = False
                self.assertEqual(function(*values).statut, "installe")
                before = target.read_bytes()
                self.assertEqual(function(*values).statut, "inchange")
                self.assertEqual(target.read_bytes(), before)
                args.uninstall = True
                self.assertEqual(function(*values).statut, "desinstalle")
                self.assertTrue(list(target.parent.glob(filename + ".bak-*")))

    def test_no_implicit_account_or_ssh_on_allocation(self):
        code = '''
from unittest.mock import patch
from romeo_mcp import cluster, slurm, outils_calcul as jobs, outils_execution as build, outils_mesure as measure
assert cluster.DEFAULT_ACCOUNT == ""
assert cluster.USER_MAX_CPUS == cluster.USER_MAX_GPUS == cluster.USER_MAX_JOBS == 0
calls = [
    (jobs, lambda: jobs.job_prepare(name="example", command="hostname")),
    (jobs, lambda: jobs.job_array_prepare(name="example", command="hostname", parameters=["one"])),
    (jobs, lambda: jobs.job_resilient_prepare(name="example", command="hostname")),
    (jobs, lambda: jobs.job_pipeline_prepare(name="example", stages=[])),
    (jobs, lambda: jobs.romeo_fairshare_forecast()),
    (build, lambda: build.compute_command_prepare(commands=["true"])),
    (measure, lambda: measure.cluster_gpu_health_run()),
]
for module, call in calls:
    with patch.object(module, "session", side_effect=AssertionError("SSH must not be reached")) as ssh:
        result = call()
        assert result["ok"] is False and "Projet ROMEO absent" in str(result), result
        ssh.assert_not_called()
for value in ("", "VOTRE_PROJET", "project\\ncommand"):
    try:
        slurm.plan_job(slurm.JobSpec(name="example", command="hostname", account=value), "/scratch_p/user")
    except cluster.ClusterError:
        pass
    else:
        raise AssertionError("invalid account accepted")
print("allocation guards passed")
'''
        result = subprocess.run([sys.executable, "-c", code], cwd=self.tmp.name,
                                env=self.env, text=True, encoding="utf-8",
                                capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_privacy_scanner_reads_index_and_all_history(self):
        repo = Path(self.tmp.name) / "fixture"
        repo.mkdir()

        def git(*args):
            subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)

        git("init")
        git("config", "user.name", "Example")
        git("config", "user.email", "example@users.noreply.github.com")
        private = "example" + "@" + "personal.invalid"
        target = repo / "example.txt"
        target.write_text(private, encoding="utf-8")
        git("add", "example.txt")
        git("commit", "-m", "Example")
        target.write_text("Clean example", encoding="utf-8")
        git("add", "example.txt")
        git("commit", "-m", "Clean")
        with patch.object(check_privacy, "ROOT", repo):
            with patch.object(sys, "argv", ["check_privacy"]):
                self.assertEqual(check_privacy.main(), 0)
            with patch.object(sys, "argv", ["check_privacy", "--history"]):
                self.assertEqual(check_privacy.main(), 1)
            target.write_text(private, encoding="utf-8")
            git("add", "example.txt")
            target.write_text("Clean working copy", encoding="utf-8")
            with patch.object(sys, "argv", ["check_privacy"]):
                self.assertEqual(check_privacy.main(), 1)
        token = "ghp_" + "a" * 40
        self.assertTrue(check_privacy.inspect_text("example.txt", token.encode()))
        self.assertTrue(check_privacy.path_issues(".ssh/id_ed25519"))

    def test_privacy_allows_only_the_public_ssh_transport_identity(self):
        remote = b"git" + b"@github.com:example/project.git"
        self.assertFalse(check_privacy.inspect_text("source.py", remote))
        self.assertTrue(check_privacy.inspect_text("commit", remote, metadata=True))
        address = b"student" + b"@github.com"
        self.assertTrue(check_privacy.inspect_text("source.py", address))
        self.assertFalse(check_privacy.inspect_text("commit", b"GitHub <noreply@github.com>", metadata=True))


class ClientApprovalTests(unittest.TestCase):
    """Les choix du client survivent aux installations et aux changements de mode."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="romeo approvals ")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.target = self.root / "config.toml"
        self.args = SimpleNamespace(
            targets="codex", codex_config=str(self.target), name="romeo",
            uninstall=False, dry_run=False, follow_client_approvals=False,
        )

    def install(self, text=None):
        if text is not None:
            self.target.write_text(text, encoding="utf-8")
        return install_mcp.installer_codex(
            "new-python", ["-m", "romeo_mcp"], {"PYTHONPATH": "new-root"}, self.args,
        )

    def server(self):
        return tomllib.loads(self.target.read_text(encoding="utf-8"))["mcp_servers"]["romeo"]

    def test_full_access_inherits_without_repeated_approval_and_is_idempotent(self):
        result = self.install('approval_policy = "never"\nsandbox_mode = "danger-full-access"\n')
        self.assertEqual(result.statut, "installe", result.detail)
        self.assertEqual(self.server()["default_tools_approval_mode"], "approve")
        before = self.target.read_bytes()
        self.assertEqual(self.install().statut, "inchange")
        self.assertEqual(self.target.read_bytes(), before)

    def test_never_alone_and_restricted_modes_do_not_grant_permission(self):
        for text in (
            '', 'approval_policy = "never"\n',
            'approval_policy = "never"\nsandbox_mode = "read-only"\n',
            'approval_policy = "never"\nsandbox_mode = "workspace-write"\n',
            'approval_policy = "on-request"\nsandbox_mode = "danger-full-access"\n',
            'approval_policy = { granular = { mcp_elicitations = false } }\nsandbox_mode = "danger-full-access"\n',
        ):
            with self.subTest(text=text):
                self.assertEqual(self.install(text).statut, "installe")
                self.assertEqual(self.server()["default_tools_approval_mode"], "auto")

    def test_selected_profile_is_used_and_unknown_profile_is_not_guessed(self):
        for profile, expected in (
            ('[profiles.chosen]\napproval_policy = "never"\nsandbox_mode = "danger-full-access"\n', "approve"),
            ('[profiles.chosen]\nsandbox_mode = "read-only"\n', "auto"),
            ('[profiles.other]\nsandbox_mode = "danger-full-access"\n', "auto"),
        ):
            with self.subTest(profile=profile):
                self.install('profile = "chosen"\napproval_policy = "never"\nsandbox_mode = "danger-full-access"\n' + profile)
                self.assertEqual(self.server()["default_tools_approval_mode"], expected)

    def test_explicit_server_and_tool_preferences_survive_reinstallation(self):
        for mode in ("auto", "prompt", "writes", "approve"):
            with self.subTest(mode=mode):
                source = '''# User configuration
approval_policy = "never"
sandbox_mode = "danger-full-access"
[mcp_servers.other]
command = "other"
[mcp_servers."romeo"] # Existing settings
command = "old-python"
default_tools_approval_mode = "%s"
enabled = false
enabled_tools = ["tool_profile_set", "cancel_job"]
disabled_tools = ["cancel_job"]
tool_timeout_sec = 120.5
startup_timeout_sec = 90
env_vars = ["TOKEN", { name = "REMOTE", source = "remote" }]
[mcp_servers.romeo.env]
PYTHONPATH = "old-root"
ROMEO_HOST = "example-host"
[mcp_servers.romeo.tools.cancel_job]
approval_mode = "prompt"
output_token_limit = 500
''' % mode
                before = tomllib.loads(source)
                result = self.install(source)
                self.assertEqual(result.statut, "installe", result.detail)
                expected = before["mcp_servers"]["romeo"]
                expected.update(command="new-python", args=["-m", "romeo_mcp"])
                expected["env"]["PYTHONPATH"] = "new-root"
                self.assertEqual(tomllib.loads(self.target.read_text(encoding="utf-8")), before)
                self.assertEqual(self.install().statut, "inchange")

    def test_inherited_preference_is_recomputed_when_client_changes(self):
        self.install('approval_policy = "never"\nsandbox_mode = "danger-full-access"\n')
        text = self.target.read_text(encoding="utf-8").replace('"danger-full-access"', '"read-only"')
        self.install(text)
        self.assertEqual(self.server()["default_tools_approval_mode"], "auto")
        text = self.target.read_text(encoding="utf-8").replace('"read-only"', '"danger-full-access"')
        self.install(text)
        self.assertEqual(self.server()["default_tools_approval_mode"], "approve")

    def test_manual_change_takes_precedence_over_generated_marker(self):
        self.install('approval_policy = "never"\nsandbox_mode = "danger-full-access"\n')
        text = self.target.read_text(encoding="utf-8").replace(
            "default_tools_approval_mode = 'approve'", "default_tools_approval_mode = 'prompt'",
        )
        self.install(text)
        self.assertEqual(self.server()["default_tools_approval_mode"], "prompt")
        self.args.follow_client_approvals = True
        self.install()
        self.assertEqual(self.server()["default_tools_approval_mode"], "approve")

    def test_dry_run_and_invalid_config_never_write(self):
        source = 'approval_policy = "never"\nsandbox_mode = "danger-full-access"\n'
        self.args.dry_run = True
        self.assertEqual(self.install(source).statut, "simule")
        self.assertEqual(self.target.read_text(encoding="utf-8"), source)
        self.assertFalse(list(self.root.glob("*.bak-*")))
        self.args.dry_run = False
        for source in ('[mcp_servers.romeo\n', 'mcp_servers = { romeo = { command = "old" } }\n'):
            with self.subTest(source=source):
                self.assertEqual(self.install(source).statut, "erreur")
                self.assertEqual(self.target.read_text(encoding="utf-8"), source)

    def test_multiline_values_and_custom_names_are_preserved(self):
        self.args.name = "romeo.test"
        source = '''description = ''' + "'''\n[mcp_servers.romeo.test]\n'''\n" + '''[mcp_servers."romeo.test"]
command = "old"
default_tools_approval_mode = "prompt"
args = [
  "old-argument",
]
[mcp_servers."romeo.test".tools."tool.name"]
approval_mode = "prompt"
'''
        result = self.install(source)
        self.assertEqual(result.statut, "installe", result.detail)
        data = tomllib.loads(self.target.read_text(encoding="utf-8"))
        self.assertEqual(data["description"], "[mcp_servers.romeo.test]\n")
        self.assertEqual(data["mcp_servers"]["romeo.test"]["tools"]["tool.name"]["approval_mode"], "prompt")
        self.assertEqual(self.install().statut, "inchange")

    def test_claude_code_native_permission_rules_are_preserved(self):
        settings = self.root / ".claude" / "settings.json"
        settings.parent.mkdir()
        for mode in ("default", "dontAsk", "bypassPermissions"):
            with self.subTest(mode=mode):
                source = json.dumps({"permissions": {"defaultMode": mode, "allow": ["mcp__romeo__*"], "ask": ["mcp__romeo__cancel_job"]}})
                settings.write_text(source, encoding="utf-8")
                (self.root / ".claude.json").write_text('{"mcpServers": {}}', encoding="utf-8")
                args = SimpleNamespace(name="romeo", scope="user", uninstall=False, dry_run=False)
                with patch.object(install_mcp.shutil, "which", return_value=None), patch.object(install_mcp.Path, "home", return_value=self.root):
                    result = install_mcp.installer_claude_code({"command": "python"}, "python", [], args)
                self.assertEqual(result.statut, "installe", result.detail)
                self.assertEqual(settings.read_text(encoding="utf-8"), source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
