"""Espaces projet : la meme regle pour chaque login, sans cluster."""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import offline  # noqa: F401,E402
from romeo_mcp import file_operations, guard, noyau, outils_donnees as data, outils_execution as execution  # noqa: E402
from romeo_mcp import plans, remote_paths, server, transfers  # noqa: F401,E402
from romeo_mcp.guard import GuardError  # noqa: E402
from romeo_mcp.slurm import JobSpec  # noqa: E402
from romeo_mcp.ssh import Result  # noqa: E402


class FakeConnection:
    """Session minimale : enregistre les commandes et simule le verrouillage."""

    host = "cluster-test"

    def __init__(self, user="alice", lock=Result(0, "2700\n", 0)):
        self.user = user
        self.home = "/home/" + user
        self.scratch = "/scratch_p/" + user
        self.path_aliases = []
        self.lock = lock
        self.commands = []

    def run(self, command, timeout=30, cwd=None, max_chars=2000):
        self.commands.append(command)
        return self.lock


class NoLogin:
    """Echoue si le login est lu alors que le chemin n'est pas dans un projet."""

    @property
    def user(self):
        raise AssertionError("login lu sans chemin de projet")


class WriteRuleTests(unittest.TestCase):
    def test_personal_folder_follows_the_session_login(self):
        for login, other in (("alice", "bob"), ("bob", "alice"), ("carol.d-e", "alice")):
            connection = SimpleNamespace(user=login)
            with self.subTest(login=login):
                guard.check_project_write("/project/demo/{}".format(login), connection)
                guard.check_project_write("/project/demo/{}/a/b".format(login), connection)
                guard.check_project_write("/gpfs/projet/demo/{}/a".format(login), connection)
                with self.assertRaisesRegex(GuardError, "/project/demo/{}/".format(login)):
                    guard.check_project_write("/project/demo/{}/a".format(other), connection)

    def test_root_and_unknown_folders_are_refused(self):
        connection = SimpleNamespace(user="alice")
        for path in ("/project", "/project/demo", "/project/demo/run.sbatch", "/project/demo/forest-1/a",
                     "/project/demo/alice-kimi/a", "/project/demo/perso/alice", "/project/demo/alice/../bob/a",
                     "/gpfs/projet/demo/x"):
            with self.subTest(path=path), self.assertRaises(GuardError):
                guard.check_project_write(path, connection)

    def test_course_and_declared_folders_stay_shared(self):
        connection = SimpleNamespace(user="alice")
        for path in ("/project/demo/chps0903/a", "/project/demo/chps0904", "/project/demo/maqao/a"):
            guard.check_project_write(path, connection)
        with self.assertRaises(GuardError):
            guard.check_project_write("/project/demo/chps/a", connection)
        with self.assertRaises(GuardError):
            guard.check_project_write("/project/demo/commun/a", connection)
        with patch.dict(os.environ, ROMEO_PROJECT_DIRS=" commun , labo-* "):
            guard.check_project_write("/project/demo/commun/a", connection)
            guard.check_project_write("/project/demo/labo-2/a", connection)

    def test_paths_outside_projects_never_read_the_login(self):
        for path in ("/scratch_p/alice/a", "/home/alice/a", "/tmp/a", "/projects/a", "/projet/a"):
            guard.check_project_write(path, NoLogin())
            self.assertIsNone(guard.personal_project_folder(path, NoLogin()))

    def test_reads_stay_free(self):
        self.assertEqual(guard.check_path("/project/demo/bob/a", "/home/alice", "/scratch_p/alice"),
                         "/project/demo/bob/a")

    def test_personal_folder_is_only_the_login_folder(self):
        connection = SimpleNamespace(user="alice")
        self.assertEqual(guard.personal_project_folder("/project/demo/alice/a/b", connection), "/project/demo/alice")
        self.assertEqual(guard.personal_project_folder("/gpfs/projet/demo/alice", connection), "/gpfs/projet/demo/alice")
        for path in ("/project/demo/bob/a", "/project/demo/chps0903/a", "/project/demo"):
            self.assertIsNone(guard.personal_project_folder(path, connection))


class PrivateFolderTests(unittest.TestCase):
    def test_lock_runs_only_for_the_personal_folder(self):
        connection = FakeConnection()
        for path in ("/scratch_p/alice/a", "/project/demo/chps0903/a"):
            remote_paths.ensure_private_folder(connection, path)
        self.assertEqual(connection.commands, [])
        remote_paths.ensure_private_folder(connection, "/project/demo/alice/a/b")
        self.assertEqual(len(connection.commands), 1)
        self.assertTrue(connection.commands[0].startswith("d=/project/demo/alice\n"))

    def test_any_other_answer_refuses_and_names_the_cause(self):
        for lock, needle in ((Result(5, "proprietaire rmadmin\n", 0), "rmadmin"), (Result(3, "lien symbolique\n", 0), "lien"),
                             (Result(4, "creation impossible\n", 0), "creation"), (Result(0, "755\n", 0), "755"),
                             (Result(0, "", 0), "aucune reponse")):
            connection = FakeConnection(lock=lock)
            with self.subTest(needle=needle), self.assertRaisesRegex(GuardError, needle):
                remote_paths.ensure_private_folder(connection, "/project/demo/alice/a")

    @unittest.skipUnless(os.name == "posix" and shutil.which("bash"), "droits POSIX requis")
    def test_lock_script_on_real_folders(self):
        def lock(folder):
            return subprocess.run(["bash", "-c", "d={}\n{}".format(folder, remote_paths.LOCK_FOLDER)],
                                  capture_output=True, text=True)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            created = root / "alice"
            self.assertEqual(lock(created).stdout.strip(), "2700")
            self.assertEqual(stat.S_IMODE(created.stat().st_mode), 0o2700)
            created.chmod(0o755)
            self.assertEqual(lock(created).stdout.strip(), "2700")
            self.assertEqual(stat.S_IMODE(created.stat().st_mode), 0o2700)
            (root / "lien").symlink_to(created)
            refused = lock(root / "lien")
            self.assertEqual(refused.returncode, 3)
            missing_parent = lock(root / "absent" / "alice")
            self.assertEqual(missing_parent.returncode, 4)


@unittest.skipUnless(os.name == "posix" and hasattr(os, "geteuid") and os.geteuid() == 0 and shutil.which("setpriv"),
                     "root et setpriv requis : vrais comptes distincts")
class RealAccountsTests(unittest.TestCase):
    OWNER, OTHER, GROUP = 61001, 61002, 61000

    def run_as(self, uid, command):
        return subprocess.run(["setpriv", "--reuid={}".format(uid), "--regid={}".format(self.GROUP), "--clear-groups",
                               "bash", "-c", command], capture_output=True, text=True, timeout=30)

    def test_other_accounts_of_the_project_group_are_denied(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as temp:
            os.chmod(temp, 0o755)
            project = Path(temp) / "demo"
            project.mkdir()
            os.chown(project, 0, self.GROUP)
            os.chmod(project, 0o2770)
            folder = project / "alice"
            lock = "d={}\n{}".format(folder, remote_paths.LOCK_FOLDER)
            self.assertEqual(self.run_as(self.OWNER, lock).stdout.strip(), "2700")
            info = folder.stat()
            self.assertEqual((stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid), (0o2700, self.OWNER, self.GROUP))
            secret = folder / "secret.txt"
            wrote = self.run_as(self.OWNER, "echo secret > {0} && cat {0}".format(secret))
            self.assertEqual(wrote.stdout.strip(), "secret", wrote.stderr)
            self.assertEqual(secret.stat().st_gid, self.GROUP, "le fichier doit garder le groupe du projet")
            for command in ("ls {}".format(folder), "cat {}".format(secret), "stat {}".format(secret),
                            "touch {}/intrus".format(folder), "rm -f {}".format(secret), "rm -rf {}".format(folder),
                            "chmod 777 {}".format(folder), "mv {} {}/copie".format(secret, project)):
                with self.subTest(command=command):
                    refused = self.run_as(self.OTHER, command)
                    self.assertNotEqual(refused.returncode, 0, refused.stdout)
                    self.assertRegex(refused.stderr, "Permission denied|Operation not permitted")
            self.assertEqual(secret.read_text().strip(), "secret")
            self.assertEqual(self.run_as(self.OTHER, lock).returncode, 5)
            self.assertEqual(stat.S_IMODE(folder.stat().st_mode), 0o2700)
            self.assertEqual(self.run_as(self.OWNER, "cat {}".format(secret)).stdout.strip(), "secret")
            # Le dossier d'un autre compte n'est jamais repris ni modifie par le verrouillage.
            owner_lock = self.run_as(self.OTHER, "d={}/bob\n{}".format(project, remote_paths.LOCK_FOLDER))
            self.assertEqual(owner_lock.stdout.strip(), "2700")
            self.assertEqual(self.run_as(self.OWNER, "d={}/bob\n{}".format(project, remote_paths.LOCK_FOLDER)).returncode, 5)
            self.assertNotEqual(self.run_as(self.OWNER, "ls {}/bob".format(project)).returncode, 0)


class LoginCommandTests(unittest.TestCase):
    connection = SimpleNamespace(user="alice")

    def written(self, command, cwd=None):
        return guard.check_project_command(command, self.connection, cwd)

    def test_reading_commands_pass(self):
        for command in ("ls -l /project/demo", "cat /project/demo/bob/a", "grep -r x /project/demo/forest-1",
                        "stat /project/demo", "cp /project/demo/bob/a /home/alice/a", "ls >&2", "ls 2>/dev/null"):
            with self.subTest(command=command):
                self.assertEqual(self.written(command, "/project/demo"), [])

    def test_writes_follow_the_rule(self):
        for command, cwd in (("mkdir /project/demo/nouveau", None), ("touch /project/demo/a", None),
                             ("touch a", "/project/demo"), ("echo x > /project/demo/a", None),
                             ("echo x >> a", "/project/demo"), ("echo x | tee /project/demo/bob/a", None),
                             ("cp /tmp/a /project/demo/a", None), ("cp -t /project/demo/bob /tmp/a", None),
                             ("cp --target-directory=/project/demo/bob /tmp/a", None),
                             ("cd /project/demo && touch a", None), ("cd /project/demo/alice; cd ..; touch a", None),
                             ("bash -c 'cd /project/demo; touch a'", None), ("touch //project/demo/a", None),
                             ("rtk bypass touch /project/demo/a", None)):
            with self.subTest(command=command), self.assertRaisesRegex(GuardError, "ecriture refusee"):
                self.written(command, cwd)

    def test_written_paths_are_returned_for_the_lock(self):
        self.assertEqual(self.written("mkdir -p /project/demo/alice/forest"), ["/project/demo/alice/forest"])
        self.assertEqual(self.written("touch a", "/project/demo/alice"), ["/project/demo/alice/a"])
        self.assertEqual(self.written("echo x > a", "/project/demo/alice"), ["/project/demo/alice/a"])
        self.assertEqual(self.written("touch /scratch_p/alice/a"), [])

    def test_tidying_moves_root_items_into_the_personal_folder(self):
        self.assertEqual(self.written("mv -n forest-1 forest-*.zip alice/forest/", "/project/demo"),
                         ["/project/demo/alice/forest"])
        self.assertEqual(self.written("mv -n -t /project/demo/alice /project/demo/run.out"), ["/project/demo/alice"])

    def test_moves_never_reach_other_folders_or_kept_ones(self):
        for command in ("mv /project/demo/forest-1 /project/demo/bob/", "mv /project/demo/forest-1 /project/demo/rangement",
                        "mv /project/demo/bob/a /project/demo/alice/", "mv /project/demo/chps0903 /project/demo/alice/",
                        "mv /project/demo/alice /tmp/a", "mv /project/demo /tmp/a", "mv * alice/"):
            with self.subTest(command=command), self.assertRaises(GuardError):
                self.written(command, "/project/demo")

    def test_deletions_and_rights_are_never_run_in_a_project(self):
        for command, cwd in (("rm /project/demo/alice/a", None), ("rm -rf /project/demo/forest-1", None),
                             ("rm a", "/project/demo/alice"), ("cd /project/demo; rm -r bob", None),
                             ("rmdir /project/demo/alice/a", None), ("unlink /project/demo/alice/a", None),
                             ("chmod 755 /project/demo/alice", None), ("chown bob /project/demo/alice/a", None),
                             ("chgrp demo /project/demo/alice/a", None), ("find /project/demo/alice -delete", None),
                             ("bash -c 'rm /project/demo/a'", None)):
            with self.subTest(command=command), self.assertRaisesRegex(GuardError, "espace projet"):
                self.written(command, cwd)

    def test_other_spaces_are_unchanged(self):
        for command in ("rm /scratch_p/alice/a", "chmod 755 /home/alice/a", "find /scratch_p/alice -name a -delete",
                        "rm a", "mv /tmp/a /tmp/b"):
            with self.subTest(command=command):
                self.assertEqual(self.written(command), [])

    def test_tool_refuses_before_running_and_locks_before_writing(self):
        connection = FakeConnection()
        with patch.object(execution, "session", return_value=connection), \
                patch.object(execution, "_sh", return_value=Result(0, "", 0)) as remote:
            refused = execution.login_command_run("rm /project/demo/alice/a")
            self.assertFalse(refused["ok"])
            self.assertTrue(refused["refused"])
            remote.assert_not_called()
            self.assertEqual(connection.commands, [])
            self.assertTrue(execution.login_command_run("mkdir /project/demo/alice/a")["ok"])
        remote.assert_called_once()
        self.assertEqual(len(connection.commands), 1)

    def test_tool_refuses_a_folder_it_cannot_lock(self):
        connection = FakeConnection(lock=Result(5, "proprietaire rmadmin\n", 0))
        with patch.object(execution, "session", return_value=connection), patch.object(execution, "_sh") as remote:
            refused = execution.login_command_run("touch /project/demo/alice/a")
        self.assertFalse(refused["ok"])
        self.assertIn("rmadmin", refused["error"])
        remote.assert_not_called()


class ToolWriteTests(unittest.TestCase):
    def test_file_tools_check_then_lock_before_writing(self):
        connection = FakeConnection()
        with self.assertRaisesRegex(GuardError, "ecriture refusee"):
            file_operations.create_file(connection, "/project/demo/a.txt", "x")
        self.assertEqual(connection.commands, [])
        connection.lock = Result(0, "2700\n", 0)
        with patch.object(connection, "run", wraps=connection.run) as run:
            run.side_effect = [Result(0, "2700\n", 0), Result(0, '{"ok": true}', 0)]
            self.assertTrue(file_operations.create_file(connection, "/project/demo/alice/a.txt", "x")["ok"])
        self.assertEqual(run.call_count, 2)
        self.assertIn("d=/project/demo/alice", run.call_args_list[0].args[0])

    def test_upload_is_refused_before_any_transfer(self):
        connection = FakeConnection()
        with tempfile.NamedTemporaryFile() as local, patch.object(data, "session", return_value=connection), \
                patch.object(data.files, "upload", side_effect=AssertionError("aucun transfert")):
            refused = data._upload_to_romeo(local.name, "/project/demo/bob/a", False)
        self.assertFalse(refused["ok"])
        self.assertIn("ecriture refusee", refused["error"])

    def test_transfers_check_only_uploads(self):
        connection = FakeConnection()
        with tempfile.TemporaryDirectory() as temp, patch.object(transfers, "session", return_value=connection), \
                patch.object(transfers, "registry", return_value=SimpleNamespace(path=Path(temp) / "jobs.db")):
            local = Path(temp) / "source.txt"
            local.write_text("x", encoding="utf-8")
            with self.assertRaisesRegex(GuardError, "ecriture refusee"):
                transfers.prepare("upload", str(local), "/project/demo/a")
            self.assertTrue(transfers.prepare("download", str(Path(temp) / "copie.txt"), "/project/demo/a")["ok"])
            self.assertTrue(transfers.prepare("upload", str(local), "/project/demo/alice/a")["ok"])


class JobPlanTests(unittest.TestCase):
    def prepare(self, connection, **fields):
        details = fields.pop("details", None)
        spec = JobSpec(name="essai", command="hostname", time="5m", arch="x64cpu", **fields)
        return plans.prepare_spec("job", spec, details=details, connection=connection,
                                  context=(connection.home, connection.scratch, [], ""))

    def test_every_written_folder_is_checked_at_preparation(self):
        connection = FakeConnection()
        self.assertTrue(self.prepare(connection, workdir="/project/demo/alice/run")["ok"])
        self.assertTrue(self.prepare(connection, workdir="/project/demo/chps0903/run")["ok"])
        self.assertTrue(self.prepare(connection)["ok"])
        for fields in ({"workdir": "/project/demo"}, {"workdir": "/project/demo/bob/run"},
                       {"checkpoint_dir": "/project/demo/ckpt"},
                       {"details": {"env_path": "/project/demo/venv"}}):
            with self.subTest(fields=fields), self.assertRaisesRegex(GuardError, "ecriture refusee"):
                self.prepare(connection, **fields)
        self.assertEqual(connection.commands, [])
        plan = SimpleNamespace(workdir="/a", spec=SimpleNamespace(checkpoint_dir="/b", checkpoint_contract={"backup_dir": "/c"}))
        self.assertEqual(plans._written_paths(plan, {"env_path": "/d"}), ["/a", "/b", "/c", "/d"])

    def test_offline_simulation_does_not_need_the_login(self):
        connection = NoLogin()
        connection.home, connection.scratch, connection.path_aliases = "/home/$USER", "/scratch_p/$USER", []
        spec = JobSpec(name="essai", command="hostname", time="5m", arch="x64cpu", workdir="/project/demo/x")
        result = plans.prepare_spec("job", spec, connection=connection,
                                    context=(connection.home, connection.scratch, [], "hors ligne"))
        self.assertEqual(result["mode"], "simulation")

    def test_submission_rechecks_and_locks_before_any_write(self):
        connection = FakeConnection(lock=Result(5, "proprietaire rmadmin\n", 0))
        prepared = self.prepare(connection, workdir="/project/demo/alice/run")
        with patch.object(plans, "session", return_value=connection), \
                patch.object(plans, "_soumettre_sbatch", side_effect=AssertionError("pas de soumission")):
            refused = plans.submit_prepared("job", prepared["plan_id"], True)
        self.assertFalse(refused["ok"])
        self.assertFalse(refused["submitted"])
        self.assertIn("rmadmin", refused["error"])
        self.assertEqual(len(connection.commands), 1)

    def test_plan_prepared_before_a_stricter_rule_is_refused(self):
        connection = FakeConnection()
        with patch.dict(os.environ, ROMEO_PROJECT_DIRS="commun"):
            prepared = self.prepare(connection, workdir="/project/demo/commun/run")
        with patch.object(plans, "session", return_value=connection), \
                patch.object(plans, "_soumettre_sbatch", side_effect=AssertionError("pas de soumission")):
            refused = plans.submit_prepared("job", prepared["plan_id"], True)
        self.assertFalse(refused["ok"])
        self.assertIn("ecriture refusee", refused["error"])


class VisibilityTests(unittest.TestCase):
    def test_rule_is_within_what_clients_keep_of_the_instructions(self):
        # Certains clients ne conservent que les 4096 premiers caracteres.
        self.assertLess(noyau.INSTRUCTIONS.index("- Espaces projet"), 200)
        end = noyau.INSTRUCTIONS.index("- Rapports MCP")
        self.assertLess(end, 1000)
        self.assertIn("mode 700", noyau.INSTRUCTIONS[:end])
        self.assertIn("mv -n", noyau.INSTRUCTIONS[:end])

    def test_cheatsheet_describes_the_rule(self):
        from romeo_mcp.cluster import cheatsheet
        self.assertIn("/project/<code_projet>/$USER", cheatsheet())


if __name__ == "__main__":
    unittest.main()
