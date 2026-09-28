"""Regressions #3 et #5 : vrais fichiers et commandes Bash, Slurm simule."""

import hashlib
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import posixpath
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import offline  # noqa: E402 - configuration fictive avant tout import du serveur
from commun import RACINE  # noqa: E402
from romeo_mcp import noyau, outils_calcul as jobs, reproducibility as repro  # noqa: E402
from romeo_mcp.cluster import ARCHS  # noqa: E402
from romeo_mcp.registry import Registry  # noqa: E402
from romeo_mcp.ssh import Result, SSHError, RomeoSession, clamp  # noqa: E402


def bash_executable():
    if os.name == "nt":
        # Le bash de System32 est un lanceur WSL, pas le shell de Git.
        git = shutil.which("git")
        if git:
            candidate = Path(git).resolve().parents[1] / "bin" / "bash.exe"
            if candidate.is_file():
                return str(candidate)
        return None
    return shutil.which("bash")


BASH = bash_executable()


class LocalSession:
    """Execute le shell localement et conserve les jobs dans une fausse file."""

    def __init__(self, root):
        self.root = root
        self.scratch = self.shell("pwd -P").stdout.strip()
        self.home = self.scratch
        self.path_aliases = []
        self.pending = []
        self.writes = []
        self.submit_barrier = None
        self.submit_lock = threading.Lock()

    def local_path(self, remote):
        relative = posixpath.relpath(remote, self.scratch)
        if relative == ".." or relative.startswith("../"):
            raise AssertionError("le test sort de son dossier temporaire")
        return self.root / relative

    def shell(self, command, cwd=None, env=None):
        return subprocess.run(
            [BASH, "--noprofile", "--norc", "-c", command],
            cwd=cwd or self.root, capture_output=True, text=True,
            encoding="utf-8", timeout=15,
            env={**os.environ, "BASH_ENV": "", **(env or {})},
        )

    def run(self, command, **kwargs):
        if command.startswith("sbatch --parsable "):
            if self.submit_barrier:
                self.submit_barrier.wait(timeout=10)
            with self.submit_lock:
                script_path = shlex.split(command)[-1]
                job_id = str(900001 + len(self.pending))
                # Comme sbatch, conserver une copie du script avant execution.
                snapshot = self.root / (job_id + ".sbatch")
                snapshot.write_bytes(self.local_path(script_path).read_bytes())
                self.pending.append((script_path, snapshot, command))
            return Result(0, job_id + "\n", 0)
        cwd = self.local_path(kwargs["cwd"]) if kwargs.get("cwd") else None
        result = self.shell(command, cwd=cwd)
        output, truncated = clamp(result.stdout + result.stderr, kwargs.get("max_chars", 12000))
        return Result(result.returncode, output, 0, truncated=truncated)

    def write_file(self, path, content, mode=None):
        target = self.local_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
        self.writes.append((path, content, mode))

    def execute_task(self, index, task_id, cwd):
        loader = ARCHS["x64cpu"]["env_loader"]
        snapshot = self.pending[index][1]
        remote_script = posixpath.join(self.scratch, snapshot.name)
        command = "{0}() {{ :; }}; export -f {0}; bash {1}".format(
            loader, shlex.quote(remote_script))
        return self.shell(command, cwd=cwd, env={"SLURM_ARRAY_TASK_ID": str(task_id)})


@unittest.skipUnless(BASH, "Bash requis (Git Bash sous Windows)")
class JobIOTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="romeo jobs ")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.session = LocalSession(self.root)
        self.enterContext(patch.object(RomeoSession, "run", side_effect=AssertionError("aucun SSH reel dans cette suite")))
        self.store = Registry(self.root / "registry.db")
        self.addCleanup(self.store.close)
        for module in (jobs, noyau):
            self.enterContext(patch.object(module, "session", return_value=self.session))
            self.enterContext(patch.object(module, "registry", return_value=self.store))
        self.enterContext(patch.object(repro, "observe_files", return_value={"git": {"status": "unavailable"}}))
        # La capture d'environnement est couverte dans test_accompagnement.
        self.enterContext(patch.object(repro, "runtime_fragment", return_value=[]))
        self.enterContext(patch.object(jobs, "_controle_du_script_genere", return_value=[]))
        self.workdir = self.session.scratch + "/campagne d'essais"

    def submit_array(self, parameters, confirm=False, **kwargs):
        plan = jobs.job_array_prepare(
            name="same-name", command='printf "fixture-result:%s\\n" "$PARAMS"',
            parameters=parameters, workdir=self.workdir, arch="x64cpu",
            **kwargs,
        )
        return jobs.job_array_submit(plan["plan_id"], confirm=True) if confirm and plan["ok"] else plan

    def test_queued_arrays_keep_their_own_parameters_and_scripts(self):
        batches = [["batch-{} row-{} 'quoted'".format(batch, row)
                    for row in range(batch % 3 + 1)] for batch in range(8)]
        self.session.submit_barrier = threading.Barrier(len(batches))
        with ThreadPoolExecutor(max_workers=len(batches)) as executor:
            submitted = list(executor.map(lambda values: self.submit_array(values, confirm=True), batches))
        for result in submitted:
            self.assertTrue(result["ok"], result)
        # Aucune tache ne demarre avant la fin des HUIT soumissions.
        for index, values in enumerate(batches):
            queued_index = int(submitted[index]["job_id"]) - 900001
            for task_id, expected in enumerate(values):
                run = self.session.execute_task(queued_index, task_id, self.session.local_path(self.workdir))
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertIn("fixture-result:" + expected + "\n", run.stdout)
        self.assertEqual(len({result["parameters_file"] for result in submitted}), len(batches))
        script_paths = [entry[0] for entry in self.session.pending]
        self.assertEqual(len(set(script_paths)), len(batches))
        for result in submitted:
            self.assertEqual(result["resolved"]["workdir"], self.workdir)
            self.assertEqual(posixpath.dirname(result["parameters_file"]), self.workdir)
        for path, snapshot, _ in self.session.pending:
            self.assertEqual(posixpath.dirname(path), self.workdir)
            self.assertEqual(self.session.local_path(path).read_bytes(), snapshot.read_bytes())

    def test_array_parameters_use_an_absolute_path(self):
        result = self.submit_array(["independent-of-cwd"], confirm=True)
        self.assertTrue(result["ok"], result)
        run = self.session.execute_task(0, 0, self.root)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("fixture-result:independent-of-cwd\n", run.stdout)

    def test_array_artifacts_have_a_checksum_in_the_job_provenance(self):
        result = self.submit_array(["sample 1", "sample 2"], confirm=True)
        self.assertTrue(result["ok"], result)
        artifacts = self.store.get_provenance(result["job_id"]).get("artifacts", {})
        self.assertIn("parameters", artifacts)
        for name, path in (("parameters", result["parameters_file"]), ("script", result["script_path"])):
            self.assertEqual(artifacts[name]["path"], path)
            self.assertEqual(artifacts[name]["sha256"], hashlib.sha256(self.session.local_path(path).read_bytes()).hexdigest())
        self.assertNotIn("sample 1", str(artifacts))

    def test_simulation_and_invalid_parameters_do_not_write_or_submit(self):
        preview = self.submit_array(["sample"], confirm=False)
        self.assertTrue(preview["ok"], preview)
        self.assertFalse(preview["submitted"])
        for invalid in ([], ["one\ntwo"], ["  "], ["one\rtwo"]):
            with self.subTest(parameters=invalid):
                self.assertFalse(self.submit_array(invalid, confirm=True)["ok"])
        self.assertEqual(self.session.writes, [])
        self.assertEqual(self.session.pending, [])

    def test_parameter_write_failure_never_submits(self):
        with patch.object(self.session, "write_file", side_effect=SSHError("fixture write failure")):
            result = self.submit_array(["sample"], confirm=True)
        self.assertFalse(result["ok"])
        self.assertEqual(self.session.pending, [])

    def test_regular_jobs_with_the_same_name_keep_distinct_scripts(self):
        for command in ("echo first", "echo second"):
            prepared = jobs.job_prepare(name="same-name", command=command, workdir=self.workdir, arch="x64cpu")
            result = jobs.job_submit(prepared["plan_id"], confirm=True)
            self.assertTrue(result["ok"], result)
        self.assertNotEqual(self.session.pending[0][0], self.session.pending[1][0])
        for path, snapshot, _ in self.session.pending:
            self.assertEqual(self.session.local_path(path).read_bytes(), snapshot.read_bytes())

    def test_resilient_chain_reuses_its_script_and_dependencies(self):
        result = jobs.submit_resilient_job(
            name="chain", command="echo resumed", segment_time="10m", max_total_time="20m",
            workdir=self.workdir, checkpoint_dir=self.session.scratch + "/checkpoints",
            arch="x64cpu", gpus_per_node=0, confirm=True,
        )
        self.assertTrue(result["ok"], result)
        self.assertEqual(len(self.session.pending), 2)
        self.assertEqual(self.session.pending[0][0], self.session.pending[1][0])
        self.assertEqual(len(self.session.writes), 1)
        self.assertIn("--dependency=afterany:" + result["job_ids"][0], self.session.pending[1][2])

    def prepare_logs(self, stderr, stdout="useful stdout\n"):
        folder = self.session.scratch + "/logs d'essais"
        if stderr is not None:
            self.session.write_file(folder + "/job_0.err", stderr)
        self.session.write_file(folder + "/job_0.out", stdout)
        self.store.record(job_id="123", name="logs", partition="instant", arch="x64cpu",
                          workdir=folder, stdout_glob=folder + "/job_*.out",
                          stderr_glob=folder + "/job_*.err", script="")
        return folder

    def test_empty_or_missing_stderr_never_counts_its_header(self):
        for stderr in (None, ""):
            self.prepare_logs(stderr)
            for stream in ("err", "both", "auto", "out"):
                with self.subTest(stderr=stderr, stream=stream):
                    result = jobs.job_log_tail("123", stream=stream)
                    self.assertTrue(result["ok"], result)
                    self.assertFalse(result["has_stderr_content"])
                    self.assertNotIn("job_0.err", result["content"])
                    if stream != "err":
                        self.assertIn("useful stdout", result["content"])
                    if stream == "auto":
                        self.assertEqual(result["stream"], "out")

    def test_whitespace_is_nonzero_bytes_but_auto_shows_useful_output(self):
        self.prepare_logs(" \t\n\n")
        result = jobs.job_log_tail("123")
        self.assertTrue(result["has_stderr_content"])
        self.assertEqual(result["stream"], "out")
        self.assertIn("useful stdout", result["content"])

    def test_real_stderr_is_reported_even_when_only_stdout_is_requested(self):
        self.prepare_logs("warning from program\n")
        result = jobs.job_log_tail("123", stream="out")
        self.assertTrue(result["has_stderr_content"])
        self.assertIn("useful stdout", result["content"])
        self.assertNotIn("warning from program", result["content"])
        result = jobs.job_log_tail("123")
        self.assertEqual(result["stream"], "err")
        self.assertIn("warning from program", result["content"])

    def test_grep_does_not_turn_headers_into_matches_or_hide_file_presence(self):
        self.prepare_logs("warning from program\n")
        result = jobs.job_log_search("123", pattern="useful")
        self.assertTrue(result["has_stderr_content"])
        self.assertEqual(result["stream"], "out")
        self.assertIn("useful stdout", result["content"])
        result = jobs.job_log_search("123", stream="err", pattern="no-match")
        self.assertTrue(result["has_stderr_content"])
        self.assertEqual(result["content"], "(aucune sortie pour l'instant)")

    def test_multiple_logs_and_missing_final_newline_preserve_user_text(self):
        folder = self.prepare_logs("")
        message = "  ### Validation ###\n--- user text\nRuntimeError: fixture"
        self.session.write_file(folder + "/job_1.err", message)
        self.session.write_file(folder + "/job_2.err", "last error")
        result = jobs.job_log_tail("123", stream="both")
        self.assertTrue(result["has_stderr_content"])
        self.assertNotIn("job_0.err", result["content"])
        self.assertIn(message, result["content"])
        self.assertIn("last error", result["content"])
        self.assertIn("useful stdout", result["content"])

    def test_tail_and_output_budget_remain_bounded(self):
        self.prepare_logs("\n".join("warning-{}".format(i) for i in range(200)))
        result = jobs.job_log_tail("123", lines=2)
        self.assertNotIn("warning-197", result["content"])
        self.assertIn("warning-199", result["content"])
        limited = jobs.job_log_tail("123", max_chars=50)
        self.assertTrue(limited["has_stderr_content"])
        self.assertLessEqual(len(limited["content"]), 80)
        self.prepare_logs("warning " * 3000)
        limited = jobs.job_log_tail("123", max_chars=50)
        self.assertTrue(limited["has_stderr_content"])
        self.assertLessEqual(len(limited["content"]), 80)


if __name__ == "__main__":
    unittest.main(verbosity=2)
