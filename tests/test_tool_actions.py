"""Contrats MCP, effets annonces et soumission exacte des plans, sans cluster."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mcp import ClientSession, StdioServerParameters, stdio_client

sys.path.insert(0, str(Path(__file__).resolve().parent))
import offline  # noqa: F401,E402
import test_job_io as io  # noqa: E402
from romeo_mcp import noyau, outils_calcul as jobs, outils_donnees as data, outils_mesure as measure  # noqa: E402
from romeo_mcp import server as assembled  # noqa: F401,E402
from romeo_mcp.registry import Registry  # noqa: E402
from romeo_mcp.ssh import Result, SSHTimeout  # noqa: E402


class ToolContractTests(unittest.TestCase):
    def test_stdio_preparation_and_confirmation_contract(self):
        async def exercise():
            with tempfile.TemporaryDirectory() as temp:
                env = {**os.environ, "ROMEO_HOME": "/home/user", "ROMEO_SCRATCH": "/scratch_p/student",
                       "ROMEO_MCP_DB": str(Path(temp) / "jobs.db"), "ROMEO_UPDATE_CHECK": "0",
                       "PYTHONIOENCODING": "utf-8", "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
                params = StdioServerParameters(command=sys.executable, args=["-m", "romeo_mcp", "serve"], env=env)
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write) as client:
                        await client.initialize()
                        response = await client.call_tool("job_prepare", {"name": "protocol", "command": "hostname"})
                        preview = json.loads(response.content[0].text)
                        self.assertTrue(preview["ok"], preview)
                        self.assertFalse(preview["submitted"])
                        self.assertTrue(preview["plan_id"])
                        refused = await client.call_tool("job_submit", {"plan_id": preview["plan_id"]})
                        payload = json.loads(refused.content[0].text)
                        self.assertFalse(payload["ok"])
                        self.assertIn("confirm=true", payload["error"])
                        missing = await client.call_tool("job_log_search", {"job_id": "123"})
                        self.assertTrue(missing.is_error)
        asyncio.run(exercise())

    def test_catalog_exposes_separate_actions_and_correct_effects(self):
        with patch.object(noyau.server, "tool_profile", "full"):
            tools = {tool.name: tool for tool in asyncio.run(noyau.server.list_tools())}
        for legacy in ("tool_profile", "job_output", "submit_job", "submit_array_job", "submit_pipeline",
                       "secret_env_setup", "run_cluster_sanity_check", "storage_cleanup_helper"):
            self.assertNotIn(legacy, tools)
        for readonly in ("tool_profile_get", "job_log_tail", "job_log_search", "storage_usage_audit"):
            self.assertTrue(tools[readonly].annotations.read_only_hint)
        for mutating in ("tool_profile_set", "secret_env_prepare", "cluster_gpu_health_run", "stage_dataset",
                         "job_prepare", "job_submit", "job_array_prepare", "job_array_submit",
                         "job_pipeline_prepare", "job_pipeline_submit"):
            self.assertFalse(tools[mutating].annotations.read_only_hint)
        self.assertEqual(tools["tool_profile_get"].input_schema["properties"], {})
        self.assertIn("profile", tools["tool_profile_set"].input_schema["required"])
        self.assertIn("pattern", tools["job_log_search"].input_schema["required"])
        self.assertNotIn("grep", tools["job_log_tail"].input_schema["properties"])
        for kind in ("job", "job_array", "job_pipeline"):
            self.assertNotIn("confirm", tools[kind + "_prepare"].input_schema["properties"])
            self.assertEqual(set(tools[kind + "_submit"].input_schema["properties"]), {"plan_id", "confirm"})

    def test_nccl_is_rejected_before_any_session_or_allocation(self):
        with patch.object(measure, "session", side_effect=AssertionError("aucune session")) as session:
            response = measure.cluster_gpu_health_run(check_type="nccl")
        self.assertFalse(response["ok"])
        self.assertIn("desactive", response["error"])
        session.assert_not_called()

    def test_gpu_probe_failure_and_empty_output_are_not_a_success(self):
        for response in (Result(1, "srun failed", 0), Result(0, "", 0),
                         Result(0, "###NOEUD romeo-a001\n", 0)):
            with patch.object(measure, "session"), patch.object(measure, "_sh", return_value=response):
                self.assertFalse(measure.cluster_gpu_health_run()["ok"])

    def test_huggingface_uses_the_selected_environment_without_installing(self):
        session = SimpleNamespace(home="/home/user", scratch="/scratch_p/student", path_aliases=[])
        with patch.object(data, "session", return_value=session), patch.object(data, "_soumettre_sbatch") as submit:
            missing = data.stage_dataset("example/dataset", "/scratch_p/student/dataset")
            self.assertFalse(missing["ok"])
            self.assertIn("romeo_pip_install", missing["error"])
            response = data.stage_dataset("example/dataset", "/scratch_p/student/dataset",
                                          env_path="/scratch_p/student/env with spaces")
            self.assertTrue(response["ok"], response)
            self.assertNotIn("pip install", response["script"])
            self.assertNotIn("--user", response["script"])
            self.assertIn("'/scratch_p/student/env with spaces/bin/python'", response["script"])
            self.assertIn("snapshot_download", response["script"])
            self.assertFalse(data.stage_dataset("example/data", "/scratch_p/student/data", env_path="/etc/env")["ok"])
            submit.assert_not_called()


@unittest.skipUnless(io.BASH, "Bash requis (Git Bash sous Windows)")
class PreparedSubmissionTests(unittest.TestCase):
    def setUp(self):
        io.JobIOTests.setUp(self)
        self.enterContext(patch.dict(os.environ, ROMEO_SCRATCH="", ROMEO_HOME=""))

    def prepare(self, **kwargs):
        response = jobs.job_prepare(name="prepared", command="echo original", workdir=self.workdir,
                                    arch="x64cpu", **kwargs)
        self.assertTrue(response["ok"], response)
        return response

    def test_exact_script_survives_restart_and_replay(self):
        preview = self.prepare()
        self.assertEqual(self.session.writes, [])
        self.assertEqual(self.session.pending, [])
        other = Registry(self.store.path)
        self.addCleanup(other.close)
        with patch.object(jobs, "registry", return_value=other), patch.object(jobs, "plan_job", side_effect=AssertionError("pas de regeneration")):
            submitted = jobs.job_submit(preview["plan_id"], confirm=True)
            self.assertTrue(submitted["ok"], submitted)
            replay = jobs.job_submit(preview["plan_id"], confirm=True)
        self.assertEqual(len(self.session.pending), 1)
        self.assertEqual(self.session.pending[0][1].read_text(encoding="utf-8"), preview["script"])
        self.assertEqual(submitted["plan_sha256"], preview["plan_sha256"])
        self.assertEqual(replay["job_id"], submitted["job_id"])
        self.assertTrue(replay["already_submitted"])

    def test_confirmation_unknown_id_and_wrong_kind_never_connect(self):
        preview = self.prepare()
        with patch.object(jobs, "session", side_effect=AssertionError("pas de SSH")):
            self.assertFalse(jobs.job_submit(preview["plan_id"])["ok"])
            self.assertFalse(jobs.job_submit("unknown", confirm=True)["ok"])
            self.assertFalse(jobs.job_array_submit(preview["plan_id"], confirm=True)["ok"])
        self.assertEqual(self.session.pending, [])
        self.assertEqual(self.session.writes, [])

    def test_expired_and_corrupted_plans_never_submit(self):
        expired = self.prepare()
        with self.store._conn:
            self.store._conn.execute("UPDATE prepared_submissions SET created_at = ? WHERE plan_id = ?",
                                     (time.time() - 90000, expired["plan_id"]))
        self.assertIn("expire", jobs.job_submit(expired["plan_id"], confirm=True)["error"])
        corrupt = self.prepare()
        with self.store._conn:
            self.store._conn.execute("UPDATE prepared_submissions SET payload = '{}' WHERE plan_id = ?",
                                     (corrupt["plan_id"],))
        self.assertIn("altere", jobs.job_submit(corrupt["plan_id"], confirm=True)["error"])
        self.assertEqual(self.session.pending, [])

    def test_changed_host_and_roots_require_a_new_plan(self):
        preview = self.prepare()
        self.session.host = "different-host"
        self.assertIn("change", jobs.job_submit(preview["plan_id"], confirm=True)["error"])
        del self.session.host
        with patch.dict(os.environ, ROMEO_SCRATCH="/scratch_p/another", ROMEO_HOME="/home/alice"):
            self.assertIn("change", jobs.job_submit(preview["plan_id"], confirm=True)["error"])
        self.assertEqual(self.session.pending, [])

    def test_concurrent_callers_cannot_submit_the_same_plan_twice(self):
        preview = self.prepare()
        with ThreadPoolExecutor(max_workers=6) as pool:
            replies = list(pool.map(lambda _: jobs.job_submit(preview["plan_id"], confirm=True), range(6)))
        self.assertTrue(any(reply["ok"] for reply in replies), replies)
        self.assertEqual(len(self.session.pending), 1)

    def test_separate_registry_connections_claim_only_once(self):
        preview = self.prepare()
        stores = [Registry(self.store.path) for _ in range(6)]
        for store in stores:
            self.addCleanup(store.close)
        with ThreadPoolExecutor(max_workers=len(stores)) as pool:
            claims = list(pool.map(lambda store: store.claim_submission(preview["plan_id"]), stores))
        self.assertEqual(sum(claims), 1)

    def test_all_pipeline_scripts_are_checked_before_any_write(self):
        preview = jobs.job_pipeline_prepare(name="lint", stages=[
            {"name": "start", "command": "true"},
            {"name": "end", "command": "true", "depends_on": ["start"]}])
        with patch.object(jobs, "_controle_du_script_genere", side_effect=[[], ["invalid second script"]]):
            result = jobs.job_pipeline_submit(preview["plan_id"], confirm=True)
        self.assertFalse(result["ok"], result)
        self.assertEqual(self.session.pending, [])
        self.assertEqual(self.session.writes, [])

    def test_lost_sbatch_reply_does_not_allow_a_second_attempt(self):
        preview = self.prepare()
        run = self.session.run
        def lost_reply(command, **kwargs):
            result = run(command, **kwargs)
            if command.startswith("sbatch "):
                raise SSHTimeout("accuse perdu")
            return result
        with patch.object(self.session, "run", side_effect=lost_reply):
            first = jobs.job_submit(preview["plan_id"], confirm=True)
        self.assertFalse(first["ok"])
        self.assertFalse(jobs.job_submit(preview["plan_id"], confirm=True)["ok"])
        self.assertEqual(len(self.session.pending), 1)

    def test_offline_illustration_has_no_executable_plan(self):
        with patch.object(jobs, "_contexte_chemins", return_value=("/home/$USER", "/scratch_p/$USER", [], "hors ligne")):
            preview = jobs.job_prepare(name="offline", command="hostname")
        self.assertTrue(preview["ok"], preview)
        self.assertIsNone(preview["plan_id"])
        self.assertFalse(preview["submittable"])
        self.assertEqual(self.session.writes, [])

    def test_array_freezes_its_script_path_and_parameter_content(self):
        parameters = ["sample 1", "sample 2"]
        preview = jobs.job_array_prepare(name="array", command='echo "$PARAMS"', parameters=parameters,
                                         workdir=self.workdir, arch="x64cpu")
        self.assertTrue(preview["ok"], preview)
        parameters[0] = "changed after preparation"
        with patch.object(jobs, "plan_job", side_effect=AssertionError("pas de regeneration")):
            submitted = jobs.job_array_submit(preview["plan_id"], confirm=True)
        self.assertTrue(submitted["ok"], submitted)
        self.assertEqual(submitted["parameters_file"], preview["parameters_file"])
        self.assertEqual(self.session.local_path(submitted["parameters_file"]).read_text(), "sample 1\nsample 2\n")
        self.assertEqual(self.session.pending[0][1].read_text(encoding="utf-8"), preview["script"])

    def test_pipeline_submits_prepared_scripts_with_dependencies(self):
        preview = jobs.job_pipeline_prepare(name="pipeline", arch="x64cpu", stages=[
            {"name": "end", "command": "echo end", "depends_on": ["start"]},
            {"name": "start", "command": "echo start"}])
        self.assertTrue(preview["ok"], preview)
        with patch.object(jobs, "plan_job", side_effect=AssertionError("pas de regeneration")):
            submitted = jobs.job_pipeline_submit(preview["plan_id"], confirm=True)
        self.assertTrue(submitted["ok"], submitted)
        for index, name in enumerate(preview["order"]):
            self.assertEqual(self.session.pending[index][1].read_text(encoding="utf-8"), preview["scripts"][name])
        self.assertIn("--dependency=afterok:" + submitted["job_ids"][0], self.session.pending[1][2])

    def test_partial_pipeline_failure_preserves_submitted_ids_and_blocks_replay(self):
        preview = jobs.job_pipeline_prepare(name="partial", stages=[
            {"name": "start", "command": "true"},
            {"name": "end", "command": "true", "depends_on": ["start"]}])
        run = self.session.run
        def fail_second(command, **kwargs):
            if command.startswith("sbatch ") and self.session.pending:
                return Result(1, "second stage refused", 0)
            return run(command, **kwargs)
        with patch.object(self.session, "run", side_effect=fail_second):
            result = jobs.job_pipeline_submit(preview["plan_id"], confirm=True)
        self.assertFalse(result["ok"], result)
        self.assertEqual(result["submitted_stages"][0]["stage"], "start")
        retry = jobs.job_pipeline_submit(preview["plan_id"], confirm=True)
        self.assertEqual(retry["previous_result"]["job_ids"], result["job_ids"])
        self.assertEqual(len(self.session.pending), 1)

    def test_log_search_validates_patterns_and_bounds_files_bytes_and_matches(self):
        folder = io.JobIOTests.prepare_logs(self, "", "old-match\n" + "x" * 1000 + "\nmatch-one\nmatch-two\n")
        self.assertFalse(jobs.job_log_search("123", "")["ok"])
        self.assertFalse(jobs.job_log_search("123", "[")["ok"])
        result = jobs.job_log_search("123", "match", max_matches=1, max_bytes_per_file=40)
        self.assertTrue(result["ok"], result)
        self.assertNotIn("old-match", result["content"])
        self.assertIn("match-one", result["content"])
        self.assertNotIn("match-two", result["content"])
        self.session.write_file(folder + "/job_1.out", "second file\n")
        limited = jobs.job_log_search("123", ".", max_files=1, max_chars=20)
        self.assertTrue(limited["files_limited"])
        self.assertLessEqual(len(limited["content"]), 20)


if __name__ == "__main__":
    unittest.main(verbosity=2)
