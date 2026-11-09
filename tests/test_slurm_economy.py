"""Economie de requetes au controleur Slurm : regroupement, reutilisation, espacement.

Chaque `squeue`, `sinfo`, `sshare` ou `scontrol` est une requete a un service
partage par tous les utilisateurs de ROMEO. Ces tests comptent les appels
reellement emis : les commandes sont executees par Bash, avec des fonctions qui
remplacent les binaires Slurm et journalisent chaque invocation. Aucun cluster.
"""
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import offline  # noqa: F401,E402  (configuration fictive avant tout import du paquet)
from romeo_mcp import energy, verification  # noqa: E402
from romeo_mcp import outils_calcul as jobs, outils_contexte as context, outils_mesure as mesure  # noqa: E402
from romeo_mcp.job_observation import LIVE_REUSE_SECONDS, parse_status, status_command  # noqa: E402
from romeo_mcp.observability import ReadCache  # noqa: E402
from romeo_mcp.registry import Registry  # noqa: E402
from romeo_mcp.ssh import Result  # noqa: E402


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


def run_with_fake_slurm(command, fakes, cwd):
    """Execute `command` ; chaque binaire de `fakes` imprime ses lignes et journalise l'appel."""
    log = Path(cwd) / "slurm-calls.log"
    log.write_text("", encoding="utf-8")
    prelude = ""
    for name, lines in fakes.items():
        body = ("printf '%s\\n' " + " ".join(shlex.quote(line) for line in lines) + ";") if lines else ":;"
        prelude += '{0}() {{ printf "%s\\n" "{0} $*" >> slurm-calls.log; {1} }}; '.format(name, body)
    result = subprocess.run([BASH, "--noprofile", "--norc", "-c", prelude + command], cwd=cwd,
                            capture_output=True, text=True, encoding="utf-8", timeout=15,
                            env={**os.environ, "BASH_ENV": "", "USER": "test-user"})
    calls = [line.split()[0] for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
    return result, calls


class Workspace(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="romeo-economy-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.store = Registry(self.root / "jobs.db")
        self.addCleanup(self.store.close)
        self.connection = SimpleNamespace(host="offline-host", user="test-user", home="/home/test",
                                          scratch="/scratch/test-user", path_aliases=[])
        self.enterContext(patch.object(jobs, "registry", return_value=self.store))
        for module in (jobs, context, mesure):
            self.enterContext(patch.object(module, "session", return_value=self.connection))
        self.enterContext(patch.object(context, "_STATUS_CACHE", ReadCache()))
        self.enterContext(patch.object(jobs, "_PENDING_CACHE", ReadCache()))

    def age_observation(self, key, seconds):
        with self.store._lock, self.store._conn:
            self.store._conn.execute("UPDATE job_observations SET observed_at = observed_at - ? WHERE job_id = ?",
                                     (seconds, key))


RUNNING = Result(0, "###LIVE\n12|test|short|RUNNING|1:00|5:00|1|node-1|(null)|2026-01-01T00:00:00|8|16G\n", 0)
PENDING = Result(0, "###LIVE\n12|test|short|PENDING|0:00|5:00|1|(Priority)|(null)|2026-01-01T03:00:00|8|16G\n", 0)


def finished(state):
    return Result(0, "###LIVE\n\n###PAST\n12|test|short|{}|1:00|0:0|start|end\n".format(state), 0)


@unittest.skipUnless(BASH, "Bash requis (Git Bash sous Windows)")
class RealShellCalls(unittest.TestCase):
    """Les commandes exactes du serveur, comptees appel par appel."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="romeo-shell-")
        self.addCleanup(temporary.cleanup)
        self.cwd = temporary.name

    def test_pending_job_costs_one_squeue_and_still_reports_its_estimated_start(self):
        line = "12|test|short|PENDING|0:00|5:00|1|(Priority)|(null)|2026-01-01T03:00:00|8|16G"
        result, calls = run_with_fake_slurm(status_command("12"), {"squeue": [line], "sacct": []}, self.cwd)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, ["squeue"])
        observed = parse_status(result.stdout, "12")
        self.assertEqual(observed["estimated_start"], "2026-01-01T03:00:00")
        self.assertEqual((observed["cpus"], observed["min_memory"]), (8, "16G"))

    def test_finished_job_costs_one_squeue_then_one_sacct(self):
        result, calls = run_with_fake_slurm(status_command("12"), {
            "squeue": [], "sacct": ["12|test|short|COMPLETED|1:00|0:0|start|end"]}, self.cwd)
        self.assertEqual(calls, ["squeue", "sacct"])
        self.assertTrue(parse_status(result.stdout, "12")["finished"])

    def test_cluster_status_reads_nodes_and_partitions_with_a_single_sinfo(self):
        fakes = {
            "sinfo": ["c1|idle|x64cpu|short*|up|1:00:00", "c1|idle|x64cpu|long|up|3-00:00:00",
                      "g1|mixed|armgpu|short*|up|1:00:00", "c2|allocated|x64cpu|long|up|3-00:00:00"],
            "sshare": ["test-project|0.1|0.5"],
            "squeue": ["12|test|short|RUNNING|1:00|5:00|c1"],
        }
        commands = []

        def shell(_session, command, **_options):
            commands.append(command)
            done, calls = run_with_fake_slurm(command, fakes, self.cwd)
            commands.append(calls)
            return Result(done.returncode, done.stdout, 0)

        connection = SimpleNamespace(host="offline-host", user="test-user")
        with patch.object(context, "session", return_value=connection), \
                patch.object(context, "_STATUS_CACHE", ReadCache()), patch.object(context, "_sh", shell):
            status = context.romeo_status()
        self.assertTrue(status["ok"], status)
        self.assertEqual(commands[1], ["sinfo", "sshare", "squeue"])
        self.assertEqual(status["nodes"]["x64cpu"]["total"], 2)
        self.assertEqual(status["nodes"]["armgpu"]["mixed"], 1)
        self.assertEqual([p["name"] for p in status["partitions"]], ["short", "long"])
        self.assertEqual(status["partitions"][1]["time_limit"], "3-00:00:00")
        self.assertEqual(len(status["my_jobs"]), 1)

    def test_drift_probe_uses_one_sinfo_and_yields_the_lines_of_the_three_former_reads(self):
        nodes = ["short*|1:00:00|x64cpu|1|192|768000|(null)", "short*|1:00:00|x64cpu|1|192|512000|(null)",
                 "short*|1:00:00|armgpu|1|288|860000|gpu:h100:4", "long|3-00:00:00|x64cpu|1|192|768000|(null)",
                 "long|3-00:00:00|x64cpu|1|192|512000|(null)"]
        result, calls = run_with_fake_slurm(verification.SONDE, {
            "sinfo": nodes, "sacctmgr": ["test-project|normal||80"]}, self.cwd)
        self.assertEqual(calls, ["sinfo", "sacctmgr"])
        lines = sorted(line for line in result.stdout.splitlines() if line.split("|")[0] in {"PART", "NODES", "ARCH"})
        # Ce que rendaient les trois `sinfo` separes sur le meme parc.
        self.assertEqual(lines, sorted([
            "PART|short*|1:00:00", "PART|long|3-00:00:00",
            "NODES|short|x64cpu|2", "NODES|short|armgpu|1", "NODES|long|x64cpu|2",
            "ARCH|x64cpu|192|768000|(null)", "ARCH|x64cpu|192|512000|(null)",
            "ARCH|armgpu|288|860000|gpu:h100:4"]))
        self.assertIn("ASSOC|test-project|normal||80", result.stdout)


class JobStatusReuse(Workspace):
    def test_recent_observation_is_reused_and_announced_as_such(self):
        with patch.object(jobs, "_sh", return_value=RUNNING) as remote:
            first = jobs.job_status("12")
            second = jobs.job_status("12")
        self.assertEqual(remote.call_count, 1)
        self.assertTrue(first["observation"]["current_state_observed"])
        self.assertEqual(second["state"], "RUNNING")
        self.assertTrue(second["observation"]["cached"])
        self.assertFalse(second["observation"]["current_state_observed"])
        self.assertLessEqual(second["observation"]["age_seconds"], LIVE_REUSE_SECONDS)

    def test_zero_age_forces_a_scheduler_read(self):
        with patch.object(jobs, "_sh", return_value=RUNNING) as remote:
            jobs.job_status("12")
            fresh = jobs.job_status("12", max_age_seconds=0)
        self.assertEqual(remote.call_count, 2)
        self.assertTrue(fresh["observation"]["current_state_observed"])

    def test_live_observation_expires(self):
        with patch.object(jobs, "_sh", return_value=PENDING) as remote:
            jobs.job_status("12")
            self.age_observation("12", LIVE_REUSE_SECONDS + 1)
            again = jobs.job_status("12")
        self.assertEqual(remote.call_count, 2)
        self.assertEqual(again["estimated_start"], "2026-01-01T03:00:00")

    def test_definitive_state_is_never_read_again_unless_forced(self):
        with patch.object(jobs, "_sh", return_value=finished("COMPLETED")) as remote:
            jobs.job_status("12")
            self.age_observation("12", 86400)
            reused = jobs.job_status("12")
            self.assertEqual(remote.call_count, 1)
            self.assertTrue(reused["finished"])
            self.assertTrue(reused["observation"]["cached"])
            jobs.job_status("12", max_age_seconds=0)
            self.assertEqual(remote.call_count, 2)

    def test_states_slurm_may_requeue_are_not_treated_as_definitive(self):
        for state in ("PREEMPTED", "NODE_FAIL", "BOOT_FAIL"):
            with self.subTest(state=state), patch.object(jobs, "_sh", return_value=finished(state)) as remote:
                jobs.job_status("12", max_age_seconds=0)
                self.age_observation("12", LIVE_REUSE_SECONDS + 1)
                jobs.job_status("12")
                self.assertEqual(remote.call_count, 2)

    def test_cancel_invalidates_the_job_and_its_array_tasks(self):
        self.store.record("12", "test", "short", "x64cpu", "/scratch/test-user", "out", "err", "script")
        task = Result(0, "###LIVE\n12_3|test|short|RUNNING|1:00|5:00|1|node-1|(null)|N/A|1|1G\n", 0)
        with patch.object(jobs, "_sh", return_value=RUNNING) as remote:
            jobs.job_status("12")
            jobs.cancel_job("12")
            after = jobs.job_status("12")
        self.assertEqual(remote.call_count, 3)
        self.assertTrue(after["observation"]["current_state_observed"])
        with patch.object(jobs, "_sh", return_value=task) as remote:
            jobs.job_status("12_3")
            jobs.cancel_job("12")
            jobs.job_status("12_3")
        self.assertEqual(remote.call_count, 3)

    def test_out_of_range_age_is_refused_before_ssh(self):
        with patch.object(jobs, "_sh") as remote:
            for age in (-1, 301):
                self.assertFalse(jobs.job_status("12", max_age_seconds=age)["ok"])
        remote.assert_not_called()

    def test_failed_read_is_never_reused(self):
        with patch.object(jobs, "_sh", return_value=Result(0, "###LIVE\n\n###PAST\n", 0)) as remote:
            self.assertFalse(jobs.job_status("12")["ok"])
            self.assertFalse(jobs.job_status("12")["ok"])
        self.assertEqual(remote.call_count, 2)


class SpacedPolling(Workspace):
    def poll(self, states, **arguments):
        clock, sleeps = [0.0], []

        def sleep(seconds):
            sleeps.append(seconds)
            clock[0] += seconds
        replies = iter(states)
        with patch.object(jobs, "job_status", side_effect=lambda _jid: next(replies)) as status, \
                patch.object(jobs.time, "monotonic", lambda: clock[0]), patch.object(jobs.time, "sleep", sleep):
            result = jobs.wait_for_job("12", **arguments)
        return result, sleeps, status.call_count

    def test_waiting_ten_minutes_costs_a_handful_of_reads(self):
        pending = [{"ok": True, "finished": False, "state": "PENDING"}] * 50
        result, sleeps, reads = self.poll(pending, timeout_seconds=600, poll_seconds=5)
        self.assertTrue(result["timed_out"])
        self.assertGreaterEqual(min(sleeps), 30)
        self.assertLessEqual(max(sleeps), 120)
        self.assertEqual(sleeps, sorted(sleeps[:-1]) + sleeps[-1:])
        self.assertLessEqual(reads, 9)

    def test_a_job_that_ends_is_reported_at_the_next_read(self):
        states = [{"ok": True, "finished": False, "state": "RUNNING"},
                  {"ok": True, "finished": True, "state": "COMPLETED"}]
        result, sleeps, reads = self.poll(states, timeout_seconds=120)
        self.assertEqual(reads, 2)
        self.assertEqual(sleeps, [30])
        self.assertEqual(result["state"], "COMPLETED")
        self.assertEqual(result["waited_seconds"], 30)

    def test_the_deadline_still_gets_a_final_read(self):
        pending = [{"ok": True, "finished": False, "state": "PENDING"}] * 10
        result, sleeps, reads = self.poll(pending, timeout_seconds=40)
        self.assertEqual(sum(sleeps), 40)
        self.assertEqual(reads, 3)


class ClusterReads(Workspace):
    STATUS = "###NODES\nn1|idle|x64cpu\n###PART\nshort|up|1:00\n###SHARE\ntest-project|0|1\n###QUEUE\n"

    def test_cluster_status_is_reused_for_thirty_seconds_by_default(self):
        with patch.object(context, "_sh", return_value=Result(0, self.STATUS, 0)) as remote:
            context.romeo_status()
            reused = context.romeo_status()
            light = context.romeo_status(include_queue=False)
            context.romeo_status(max_age_seconds=0)
        self.assertEqual(remote.call_count, 2)
        self.assertTrue(reused["observation"]["cached"])
        self.assertTrue(light["observation"]["cached"])
        self.assertIsNone(light["my_jobs"])

    def test_slot_advice_reuses_the_cluster_view_and_the_pending_queue(self):
        view = {"ok": True, "nodes": {"x64cpu": {"idle": 2, "mixed": 0}}}
        with patch.object(jobs, "romeo_status", return_value=view) as status, \
                patch.object(jobs, "_sh", return_value=Result(0, "short|1\nlong|2\n", 0)) as remote:
            first = jobs.suggest_submission_slot()
            second = jobs.suggest_submission_slot(hours=2)
        self.assertTrue(first["ok"] and second["ok"])
        self.assertEqual(remote.call_count, 1)
        self.assertTrue(second["queue_observation"]["cached"])
        self.assertEqual(status.call_args.kwargs, {"include_queue": False, "max_age_seconds": 60})


class DuplicateReads(Workspace):
    def test_system_health_takes_cores_and_memory_from_the_status_read(self):
        etat = {"ok": True, "state": "RUNNING", "cpus": 8, "min_memory": "16G",
                "reason_or_nodelist": "node-1", "elapsed": "1:00"}
        commands = []

        def shell(_session, command, **_options):
            commands.append(command)
            return Result(0, "12.batch|00:01|100M|200M|1M|1M|1\n", 0)
        probe = Result(0, "###LOAD\n1.0 1.0 1.0\n###IOWAIT\n1 100\n###PROC\n790\n", 0)
        with patch.object(mesure, "job_status", return_value=etat), patch.object(mesure, "_sh", shell), \
                patch.object(mesure, "_srun_overlap", return_value=probe):
            health = mesure.job_system_health("12")
        self.assertTrue(health["ok"], health)
        self.assertEqual(health["coeurs_alloues"], 8)
        self.assertEqual(health["memoire_demandee"], "16G")
        self.assertEqual(len(commands), 1)
        self.assertTrue(commands[0].startswith("sstat "))

    def test_energy_configuration_is_read_once_per_cache(self):
        def runner(command, **_options):
            if "--helpformat" in command:
                return SimpleNamespace(ok=True, stdout="JobID ConsumedEnergyRaw")
            if "scontrol" in command:
                return SimpleNamespace(ok=True, stdout="AcctGatherEnergyType = acct_gather_energy/ipmi")
            return SimpleNamespace(ok=True, stdout="123|COMPLETED|3600|8|cpu=8|0|2026-01-01T00:00:00|2026-01-01T01:00:00|")
        calls = []

        def read(command, **options):
            calls.append(command)
            return runner(command, **options)
        cache = {}
        for _ in range(3):
            result = energy.footprint("123", read, carbon_source="none", config_cache=cache)
            self.assertTrue(result["measurement"]["energy_plugin_enabled_now"])
        self.assertEqual(sum("scontrol" in command for command in calls), 1)
        energy.footprint("123", read, carbon_source="none")
        self.assertEqual(sum("scontrol" in command for command in calls), 2)

    def test_final_efficiency_is_reused_but_a_running_one_is_not(self):
        table = ("JobID|JobName|Partition|State|ExitCode|Elapsed|TotalCPU|AllocCPUS|ReqMem|MaxRSS|AllocTRES\n"
                 "12|test|short|{}|0:0|00:10:00|00:40:00|8|16G||cpu=8\n"
                 "12.batch|batch||{}|0:0|00:10:00|00:40:00|8||4G|cpu=8\n")
        with patch.object(jobs, "_sh", return_value=Result(0, table.format("COMPLETED", "COMPLETED"), 0)) as remote:
            jobs.job_efficiency("12")
            reused = jobs.job_efficiency("12")
            self.assertEqual(remote.call_count, 1)
            self.assertTrue(reused["observation"]["cached"])
            jobs.job_efficiency("12", refresh=True)
            self.assertEqual(remote.call_count, 2)
        with patch.object(jobs, "_sh", return_value=Result(0, table.format("RUNNING", "RUNNING"), 0)) as remote:
            jobs.job_efficiency("12", refresh=True)
            jobs.job_efficiency("12")
            self.assertEqual(remote.call_count, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
