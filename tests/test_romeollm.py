"""Integration RomeoLLMTool : CLI fictive, registre reel et protocole MCP."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shlex
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import offline  # noqa: F401 - configuration fictive avant tout import applicatif
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from romeo_mcp import romeollm as llm
from romeo_mcp.registry import Registry
from romeo_mcp.ssh import Result, SSHTimeout
from romeo_mcp.server import server


class RomeoLLMTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Registry(Path(self.temp.name) / "plans.db")
        self.addCleanup(lambda: self.store.close())
        self.session = SimpleNamespace(host="romeo-test", user="user", home="/home/user")
        self.calls = []
        self.config = "name: example\nengine: vllm\nmodel: example/model\n"
        self.script = "#!/bin/bash\n#SBATCH --time=01:00:00\nserve-model\n"
        self.launch_result = Result(0, "Submitted batch job 12345\n", 0)
        self.catalog_truncated = False
        self.script_truncated = False
        session_patch = patch.object(llm, "session", return_value=self.session)
        registry_patch = patch.object(llm, "registry", side_effect=lambda: self.store)
        ssh_patch = patch.object(llm, "_sh", side_effect=self.remote)
        env_patch = patch.dict(os.environ, {"ROMEO_LLM_EXECUTABLE": "romeollmtool"})
        for patcher in (session_patch, registry_patch, ssh_patch, env_patch):
            patcher.start()
            self.addCleanup(patcher.stop)

    def remote(self, session, command, **kwargs):
        body = command.split("; then\n", 1)[1].rsplit("\nelse", 1)[0]
        argv = shlex.split(body)[2:]
        args = argv[1:]
        self.calls.append((argv, kwargs))
        if args[:2] == ["catalog", "show"]:
            return Result(0, self.config, 0, self.catalog_truncated)
        if args[0] == "launch":
            if "--dry-run" in args:
                return Result(0, self.script, 0, self.script_truncated)
            if isinstance(self.launch_result, Exception):
                raise self.launch_result
            return self.launch_result
        if args[:2] in (["gateway", "status"], ["endpoint", "12345"]):
            return Result(0, "URL: http://login.test:11361/v1\nAPI key: fictional-private-value\n", 0)
        return Result(0, "done\n", 0)

    def prepare(self, **kwargs):
        result = llm.prepare_launch("example", None, "1h", None, **kwargs)
        self.assertTrue(result["ok"], result)
        return result

    def launches(self):
        return [args for args, _ in self.calls if args[1] == "launch" and "--dry-run" not in args]

    def test_prepare_reads_config_and_dry_run_without_submitting(self):
        plan = self.prepare()
        self.assertFalse(plan["submitted"])
        self.assertEqual(self.launches(), [])
        self.assertTrue(all(options["read_only"] for _, options in self.calls))
        self.assertIn("--no-wait", self.calls[-1][0])
        self.assertIn("--project-code test-project", plan["command"])
        self.assertEqual(self.store.prepared_submission(plan["plan_id"])["state"], "ready")

    def test_explicit_account_duration_and_reservation(self):
        plan = llm.prepare_launch("example", "other-project", "90m", "reserved-test")
        self.assertTrue(plan["ok"], plan)
        self.assertIn("--time 01:30:00", plan["command"])
        self.assertIn("--reservation reserved-test", plan["command"])

    def test_launch_confirmation_refused_before_any_ssh(self):
        self.assertFalse(llm.launch("not-a-plan", False)["ok"])
        self.assertEqual(self.calls, [])

    def test_launch_is_once_and_persisted_across_reconnection(self):
        plan = self.prepare()
        first = llm.launch(plan["plan_id"], True)
        self.assertTrue(first["ok"], first)
        self.assertEqual(first["job_id"], "12345")
        self.assertIsNone(first["ready"])
        self.assertFalse(first["result_validated"])
        self.store.close()
        self.store = Registry(Path(self.temp.name) / "plans.db")
        second = llm.launch(plan["plan_id"], True)
        self.assertTrue(second["already_executed"])
        self.assertEqual(len(self.launches()), 1)
        self.assertFalse(self.calls[-1][1]["read_only"])

    def test_changed_fiche_is_refused_without_consuming_or_launching(self):
        plan = self.prepare()
        self.config += "gpus: 8\n"
        result = llm.launch(plan["plan_id"], True)
        self.assertFalse(result["ok"])
        self.assertIn("change", result["error"])
        self.assertEqual(self.launches(), [])
        self.assertEqual(self.store.prepared_submission(plan["plan_id"])["state"], "ready")

    def test_successful_cli_without_slurm_receipt_does_not_invent_job_or_readiness(self):
        plan = self.prepare()
        self.launch_result = Result(0, "Lancement demande\n", 0)
        result = llm.launch(plan["plan_id"], True)
        self.assertTrue(result["command_succeeded"])
        self.assertFalse(result["submission_observed"])
        self.assertNotIn("job_id", result)
        self.assertIsNone(result["ready"])

    def test_expired_or_wrong_kind_plan_is_refused(self):
        plan = self.prepare()
        with self.store._conn:
            self.store._conn.execute("UPDATE prepared_submissions SET created_at=0")
        self.assertFalse(llm.launch(plan["plan_id"], True)["ok"])
        wrong = self.store.prepare_submission({"kind": "job"})
        self.assertFalse(llm.launch(wrong["plan_id"], True)["ok"])
        self.assertEqual(self.launches(), [])

    def test_changed_ssh_target_or_executable_is_refused(self):
        for field in ("host", "user", "home"):
            plan = self.prepare()
            original = getattr(self.session, field)
            setattr(self.session, field, "changed")
            self.assertFalse(llm.launch(plan["plan_id"], True)["ok"])
            setattr(self.session, field, original)
        plan = self.prepare()
        with patch.dict(os.environ, {"ROMEO_LLM_EXECUTABLE": "/apps/another-tool"}):
            self.assertFalse(llm.launch(plan["plan_id"], True)["ok"])
        self.assertEqual(self.launches(), [])

    def test_incomplete_preparations_never_produce_executable_plan(self):
        for field, value in (("catalog_truncated", True), ("script_truncated", True), ("script", "")):
            old = getattr(self, field)
            setattr(self, field, value)
            result = llm.prepare_launch("example", None, "1h", None)
            self.assertFalse(result["ok"])
            self.assertNotIn("plan_id", result)
            setattr(self, field, old)

    def test_ssh_cut_nonzero_and_truncation_consume_plan_without_replay(self):
        for outcome in (SSHTimeout("private message"), Result(1, "sbatch response lost", 0), Result(0, "partial", 0, True)):
            with self.subTest(outcome=type(outcome).__name__):
                plan = self.prepare()
                self.launch_result = outcome
                result = llm.launch(plan["plan_id"], True)
                self.assertFalse(result["ok"], result)
                self.assertEqual(result["execution_outcome"], "unknown")
                self.assertFalse(result["retry_safe"])
                self.assertEqual(self.store.prepared_submission(plan["plan_id"])["state"], "uncertain")
                before = len(self.launches())
                self.assertFalse(llm.launch(plan["plan_id"], True)["ok"])
                self.assertEqual(len(self.launches()), before)
                self.assertNotIn("private message", json.dumps(result))

    def test_concurrent_launches_do_not_submit_twice(self):
        plan = self.prepare()
        def invoke(_):
            try:
                return llm.launch(plan["plan_id"], True)
            except ValueError:
                return {"ok": False}
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(invoke, range(2)))
        self.assertTrue(any(result["ok"] for result in outcomes))
        self.assertEqual(len(self.launches()), 1)

    def test_gateway_stop_always_preserves_jobs_and_needs_confirmation(self):
        self.assertFalse(llm.gateway_stop(False)["ok"])
        self.assertEqual(self.calls, [])
        self.assertTrue(llm.gateway_stop(True)["ok"])
        self.assertEqual(self.calls[-1][0][1:], ["gateway", "stop", "--keep-jobs"])
        self.assertFalse(self.calls[-1][1]["read_only"])

    def test_gateway_start_is_bounded_and_explicit(self):
        self.assertTrue(llm.gateway_start(None, 8, True)["ok"])
        self.assertEqual(self.calls[-1][0][1:], ["gateway", "start", "--hours", "8"])
        for args in ((80, 8, True), (None, 25, True), (True, 8, True)):
            with self.assertRaises(ValueError):
                llm.gateway_start(*args)

    def test_only_numeric_job_ids_can_stop_or_read_logs(self):
        for target in ("--all", "example", "123; touch bad", "0", "1\n2"):
            with self.assertRaises(ValueError):
                llm.stop(target, True)
            with self.assertRaises(ValueError):
                llm.logs(target, 50)
        self.assertEqual(self.calls, [])
        self.assertTrue(llm.stop("12345", True)["ok"])
        llm.logs("12345", 100)
        self.assertEqual(self.calls[-1][0][1:], ["logs", "12345", "-n", "100"])

    def test_chat_is_one_shot_quoted_and_never_starts_model(self):
        message = "Bonjour 'x'; $(touch injected)\nnext line"
        result = llm.chat("example/model", message, 256, 45)
        self.assertTrue(result["ok"])
        args, options = self.calls[-1]
        self.assertEqual(args[args.index("-m") + 1], message)
        self.assertIn("--no-stream", args)
        self.assertIn("--hide-think", args)
        self.assertEqual(options["timeout"], 45)
        self.assertFalse(options["read_only"])
        self.assertEqual(self.launches(), [])

    def test_invalid_inputs_are_refused_before_ssh(self):
        invalid = [lambda: llm.catalog("--help", None), lambda: llm.catalog("example", "vision"),
            lambda: llm.prepare_launch("example;bad", None, "1h", None),
            lambda: llm.prepare_launch("example", None, "25h", None),
            lambda: llm.prepare_launch("example", None, "30s", None),
            lambda: llm.stats(True), lambda: llm.stats(0), lambda: llm.logs("123", 501),
            lambda: llm.chat("--bad", "message", 1, 5), lambda: llm.chat("model", "", 1, 5),
            lambda: llm.chat("model", "message", 0, 5), lambda: llm.chat("model", "message", 1, 91)]
        for call in invalid:
            with self.assertRaises(ValueError):
                call()
        self.assertEqual(self.calls, [])

    def test_endpoint_hides_keys_and_builds_tunnel_from_observed_url(self):
        result = llm.endpoint("12345", 12000)
        self.assertTrue(result["ok"], result)
        self.assertNotIn("fictional-private-value", json.dumps(result))
        self.assertFalse(result["api_key_exposed"])
        self.assertEqual(result["api_key_scope"], "gateway_only")
        self.assertFalse(result["connections"][0]["authentication_verified"])
        self.assertEqual(result["connections"][0]["local_url"], "http://localhost:12000/v1")
        self.assertIn("12000:login.test:11361", result["connections"][0]["ssh_tunnel_command"])
        self.assertFalse(result["connections"][0]["tunnel_opened"])
        self.assertNotIn("--show-key", self.calls[-1][0])

    def test_secrets_in_preview_and_logs_are_not_persisted(self):
        self.config += "api_key: fictional-secret-one\n"
        self.script += "API key: fictional-secret-two\nClé API : fictional-secret-three\n"
        plan = self.prepare()
        stored = self.store.prepared_submission(plan["plan_id"])
        text = json.dumps([stored, plan])
        for secret in ("fictional-secret-one", "fictional-secret-two", "fictional-secret-three"):
            self.assertNotIn(secret, text)

    def test_missing_cli_is_an_actionable_error(self):
        with patch.object(llm, "_sh", return_value=Result(127, llm._MISSING, 0)):
            result = llm.inspect("status")
        self.assertFalse(result["ok"])
        self.assertFalse(result["available"])
        self.assertIn("ROMEO_LLM_EXECUTABLE", result["next_step"])

    def test_custom_executable_is_a_single_quoted_path(self):
        value = "/apps/llm tools/romeollmtool"
        with patch.dict(os.environ, {"ROMEO_LLM_EXECUTABLE": value}):
            llm.inspect("status")
        self.assertEqual(self.calls[-1][0][0], value)

    def test_truncated_gateway_output_does_not_generate_tunnel(self):
        with patch.object(llm, "_sh", return_value=Result(0, "http://login.test:1234/v1", 0, True)):
            result = llm.gateway_status(12000)
        self.assertFalse(result["complete"])
        self.assertNotIn("connections", result)


class ProtocolTests(unittest.TestCase):
    def test_capabilities_exposes_llm_group_and_essential_visibility(self):
        from romeo_mcp.outils_diagnostics import romeo_capabilities
        with patch.object(server, "tool_profile", "essential"):
            result = romeo_capabilities(task="llm")
        tools = result["groups"][0]["tools"]
        self.assertEqual(result["groups"][0]["task"], "llm")
        self.assertEqual(len(tools), 14)
        self.assertEqual(sum(tool["visible"] for tool in tools), 11)
        self.assertFalse(result["ssh_connection_observed"])

    def test_catalog_annotations_and_schema(self):
        tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}
        names = {name for name in tools if name.startswith("romeollm_")}
        self.assertEqual(len(names), 14)
        for name in names:
            readonly = name in {"romeollm_catalog", "romeollm_status", "romeollm_engines", "romeollm_doctor",
                                "romeollm_stats", "romeollm_logs", "romeollm_endpoint", "romeollm_gateway_status"}
            self.assertEqual(tools[name].annotations.read_only_hint, readonly, name)
        self.assertTrue(tools["romeollm_stop"].annotations.destructive_hint)
        self.assertEqual(set(tools["romeollm_launch"].input_schema["properties"]), {"plan_id", "confirm"})

    def test_real_stdio_catalog_and_refusal_without_ssh(self):
        async def exercise():
            with tempfile.TemporaryDirectory() as temp:
                env = {**os.environ, "ROMEO_TOOL_PROFILE": "essential", "ROMEO_UPDATE_CHECK": "0",
                    "ROMEO_MCP_DB": str(Path(temp) / "state.db"), "PYTHONIOENCODING": "utf-8"}
                params = StdioServerParameters(command=sys.executable, args=["-m", "romeo_mcp", "serve"], env=env)
                async with stdio_client(params) as (read, write):
                    async with ClientSession(read, write) as client:
                        await client.initialize()
                        names = {tool.name for tool in (await client.list_tools()).tools}
                        self.assertIn("romeollm_launch_prepare", names)
                        self.assertIn("romeollm_chat", names)
                        reply = await client.call_tool("romeollm_launch", {"plan_id": "a" * 32})
                        self.assertFalse(json.loads(reply.content[0].text)["ok"])
                        reply = await client.call_tool("romeollm_gateway_start", {})
                        self.assertFalse(json.loads(reply.content[0].text)["ok"])
                        invalid = await client.call_tool("romeollm_chat", {"model": "test", "message": "test", "max_tokens": 0})
                        self.assertTrue(invalid.is_error)
        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
