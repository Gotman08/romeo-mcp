"""Installation neuve, configuration privee et garde-fous de publication."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
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
    (jobs, lambda: jobs.submit_job(name="example", command="hostname")),
    (jobs, lambda: jobs.submit_array_job(name="example", command="hostname", parameters=["one"])),
    (jobs, lambda: jobs.submit_resilient_job(name="example", command="hostname")),
    (jobs, lambda: jobs.submit_pipeline(name="example", stages=[])),
    (jobs, lambda: jobs.romeo_fairshare_forecast()),
    (build, lambda: build.build_on_node(commands=["true"])),
    (measure, lambda: measure.run_cluster_sanity_check()),
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
