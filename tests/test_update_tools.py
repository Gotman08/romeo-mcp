"""Mises a jour pilotables : autorisation, etats persistants et protocole reel."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from test_updates import TemporaryInstallation, release
from romeo_mcp import updates as u, update_service as service, update_worker as worker


class UpdateToolTests(TemporaryInstallation):
    def setUp(self):
        super().setUp()
        self.release = release()
        patch.dict(os.environ, ROMEO_AUTO_UPDATE="").start()
        os.environ.pop("ROMEO_AUTO_UPDATE", None)
        patch.object(u, "latest_release", return_value=self.release).start()
        patch.object(u, "installation", return_value=self.target).start()

    def launch(self, **kwargs):
        with patch.object(service.subprocess, "Popen", return_value=Mock(pid=123)):
            return service.start(True, target=self.target, **kwargs)

    def test_network_error_is_unknown_cached_and_retried(self):
        with patch.object(u, "latest_release", side_effect=u.UpdateError("GitHub indisponible")) as fetch:
            first = service.check(target=self.target)
            second = service.check(target=self.target)
            self.assertEqual(fetch.call_count, 1)
            self.assertFalse(first["ok"])
            self.assertIsNone(first["update_available"])
            self.assertIn("inconnue", second["message"])
            service.check(True, target=self.target)
            self.assertEqual(fetch.call_count, 2)
        cached = u._read_json(self.target.root / "check.json")
        cached["checked_at"] -= service.RETRY_TTL + 1
        u._write_json(self.target.root / "check.json", cached)
        self.assertTrue(service.check(target=self.target)["update_available"])

    def test_cache_success_and_no_release_are_distinct(self):
        with patch.object(u, "latest_release", return_value=None) as fetch:
            self.assertFalse(service.check(target=self.target)["update_available"])
            self.assertIsNone(service.check(target=self.target)["latest_version"])
            self.assertEqual(fetch.call_count, 1)
        self.assertEqual(service.check(True, target=self.target)["latest_version"], "9.0.0")

    def test_cached_or_planned_untrusted_release_rejected(self):
        bad = {**self.release, "url": "https://example.org/foreign.whl"}
        u._write_json(self.target.root / "check.json", {"schema": 2, "checked_at": time.time(), "release": bad, "error": None})
        with self.assertRaisesRegex(u.UpdateError, "officielle"):
            service.check(target=self.target)
        with self.assertRaisesRegex(u.UpdateError, "officielle"):
            u.apply_release(self.target, bad, self.target.state())
        self.assertIsNone(self.target.state()["active"])

    def test_automatic_authorization_persists_and_environment_overrides(self):
        with self.assertRaises(u.UpdateError):
            service.configure(True, target=self.target)
        result = service.configure(True, True, target=self.target)
        self.assertTrue(result["automatic_enabled"])
        self.assertTrue(service.policy(self.target)["automatic_enabled"])
        with patch.dict(os.environ, ROMEO_AUTO_UPDATE="0"):
            result = service.configure(True, True, target=self.target)
            self.assertFalse(result["automatic_enabled"])
            self.assertTrue(result["saved_automatic"])
        service.configure(False, True, target=self.target)
        self.assertFalse(service.policy(self.target)["automatic_enabled"])

    def test_no_authorization_or_changed_announcement_does_not_launch(self):
        with patch.object(service.subprocess, "Popen") as spawn:
            with self.assertRaises(u.UpdateError):
                service.start(target=self.target)
            with self.assertRaisesRegex(u.UpdateError, "change"):
                service.start(True, "8.0.0", target=self.target)
            spawn.assert_not_called()

    def test_start_detaches_and_repeated_request_does_not_duplicate(self):
        with patch.dict(os.environ, ROMEO_ACCOUNT="test-project", ROMEO_HOST="invalid-offline-host"), \
             patch.object(service.subprocess, "Popen", return_value=Mock(pid=123)) as spawn:
            result = service.start(True, "9.0.0", target=self.target)
            options = spawn.call_args.kwargs
            self.assertEqual(options["stdout"], subprocess.DEVNULL)
            self.assertEqual(options["stderr"], subprocess.DEVNULL)
            self.assertNotIn("ROMEO_ACCOUNT", options["env"])
            self.assertNotIn("ROMEO_HOST", options["env"])
            self.assertFalse(result["result_validated"])
            self.assertTrue(result["started"])
            again = service.start(True, target=self.target)
            self.assertTrue(again["already_started"])
            self.assertEqual(again["operation"]["operation_id"], result["operation_id"])
            self.assertEqual(spawn.call_count, 1)
            self.assertEqual(u.latest_release.call_count, 1)

    def test_worker_result_survives_reconnection_and_already_selected_is_not_reinstalled(self):
        result = self.launch()
        directory = service._operation_path(self.target, result["operation_id"])
        with patch.object(u, "_download"), patch.object(u, "_run"), patch.object(u, "health_check", return_value="9.0.0"):
            self.assertEqual(worker.run(directory / "plan.json"), 0)
        current = service.status(target=self.target)
        self.assertEqual(current["operation"]["state"], "ready")
        self.assertTrue(current["operation"]["result_validated"])
        self.assertEqual(current["next_start_version"], "9.0.0")
        self.assertEqual(current["running_version"], u.__version__)
        self.assertTrue(current["restart_required"])
        # Le test de preparation simule les sous-processus, creer leur executable.
        executable = self.target.executable(self.target.state()["active"])
        executable.parent.mkdir(parents=True)
        executable.touch()
        with patch.object(service.subprocess, "Popen") as spawn:
            self.assertFalse(service.start(True, target=self.target)["started"])
            spawn.assert_not_called()
        self.assertFalse(service.check(target=self.target)["installation_needed"])

    def test_failed_worker_keeps_selection_and_does_not_announce_ready(self):
        before = self.target.state()
        launched = self.launch()
        directory = service._operation_path(self.target, launched["operation_id"])
        with patch.object(u, "_download", side_effect=u.UpdateError("empreinte incorrecte")):
            self.assertEqual(worker.run(directory / "plan.json"), 1)
        observed = service.status(target=self.target)
        self.assertFalse(observed["ok"])
        self.assertEqual(observed["operation"]["state"], "failed")
        self.assertFalse(observed["operation"]["result_validated"])
        self.assertEqual(self.target.state(), before)
        self.assertIn("empreinte", observed["message"])

    def test_launch_failure_is_recoverable_without_pointer_change(self):
        with patch.object(service.subprocess, "Popen", side_effect=OSError("fixture")):
            with self.assertRaises(u.UpdateError):
                service.start(True, target=self.target)
        self.assertEqual(service.status(target=self.target)["operation"]["state"], "launch_failed")
        self.assertIsNone(self.target.state()["active"])
        self.assertTrue(self.launch()["started"])

    def test_interruption_is_not_success_and_lock_prevents_false_interruption(self):
        launched = self.launch()
        directory = service._operation_path(self.target, launched["operation_id"])
        observed = u._read_json(directory / "status.json")
        observed["updated_at"] -= service.LAUNCH_GRACE + 1
        u._write_json(directory / "status.json", observed)
        with u.file_lock(self.target.root / "update.lock"):
            current = service.status(target=self.target)
            self.assertTrue(current["operation"]["transaction_lock_held"])
            self.assertEqual(current["operation"]["state"], "launching")
            self.assertTrue(service.start(True, target=self.target)["already_started"])
        current = service.status(target=self.target)
        self.assertEqual(current["operation"]["state"], "interrupted")
        self.assertFalse(current["ok"])
        self.assertFalse(current["operation"]["result_validated"])
        self.assertTrue(self.launch()["started"])

    def test_superseded_or_altered_plan_cannot_install(self):
        first = self.launch()
        directory = service._operation_path(self.target, first["operation_id"])
        u._write_json(self.target.root / "operation.json", {"operation_id": "a" * 32})
        with patch.object(u, "apply_release") as apply:
            self.assertEqual(worker.run(directory / "plan.json"), 1)
            apply.assert_not_called()
        plan = u._read_json(directory / "plan.json")
        plan["release"]["version"] = "9.1.0"
        u._write_json(directory / "plan.json", plan)
        with self.assertRaisesRegex(u.UpdateError, "altere"):
            worker.run(directory / "plan.json")

    def test_rollback_holds_rejected_version_and_explicit_policy_clears_hold(self):
        before = self.prepared()
        service.configure(True, True, target=self.target)
        with patch.object(u, "health_check", return_value="1.0.0"):
            u.rollback(self.target, before)
        self.assertEqual(service.policy(self.target)["held_version"], "8.0.0")
        from test_updates import release_payload
        import io
        payload = release_payload(version="8.0.0")
        with patch.object(u, "_request", return_value=io.BytesIO(json.dumps(payload).encode())), \
             patch.object(u, "latest_release", wraps=type(self).real_latest_release):
            checked = service.check(True, target=self.target)
        self.assertTrue(checked["automatic_held"])
        with patch.object(service, "start") as start:
            service.startup(self.target)
            start.assert_not_called()
        with patch.object(u, "latest_release", return_value=self.release):
            self.assertFalse(service.check(True, target=self.target)["automatic_held"])
        service.configure(True, True, target=self.target)
        self.assertIsNone(service.policy(self.target)["held_version"])

    real_latest_release = staticmethod(u.latest_release)

    def test_rollback_worker_preserves_environment_only_automatic_authorization(self):
        self.prepared()
        with patch.dict(os.environ, ROMEO_AUTO_UPDATE="1"), \
             patch.object(service.subprocess, "Popen", return_value=Mock(pid=123)) as spawn:
            result = service.start(True, revert=True, target=self.target)
            child_env = spawn.call_args.kwargs["env"]
            self.assertEqual(child_env["ROMEO_AUTO_UPDATE"], "1")
            directory = service._operation_path(self.target, result["operation_id"])
            with patch.dict(os.environ, child_env, clear=True), \
                 patch.object(u, "health_check", return_value="1.0.0"):
                self.assertEqual(worker.run(directory / "plan.json"), 0)
            self.assertEqual(service.policy(self.target)["held_version"], "8.0.0")
            self.assertTrue(service.policy(self.target)["automatic_enabled"])

    def test_automatic_start_only_with_saved_authorization_and_failure_backoff(self):
        with patch.object(service, "start") as start:
            service.startup(self.target)
            start.assert_not_called()
        service.configure(True, True, target=self.target)
        with patch.object(service.subprocess, "Popen", side_effect=OSError("fixture")):
            self.assertFalse(service.startup(self.target)["ok"])
        with patch.object(service, "start") as start:
            result = service.startup(self.target)
            self.assertFalse(result["automatic_started"])
            start.assert_not_called()
        path = service._operation_path(self.target, result["operation"]["operation_id"]) / "status.json"
        observed = u._read_json(path)
        observed["updated_at"] -= service.RETRY_TTL + 1
        u._write_json(path, observed)
        with patch.object(service.subprocess, "Popen", return_value=Mock(pid=123)):
            self.assertTrue(service.startup(self.target)["automatic_started"])

    def test_invalid_operation_id_refused(self):
        for value in ("../private", "wrong", "" + "a" * 33):
            with self.assertRaises(u.UpdateError):
                service.status(value, target=self.target)

    def test_atomic_windows_sharing_retry_preserves_complete_json(self):
        path = self.target.root / "status.json"
        u._write_json(path, {"state": "before"})
        replace = os.replace
        calls = []
        def sharing(source, destination):
            calls.append(True)
            if len(calls) == 1:
                self.assertEqual(u._read_json(path), {"state": "before"})
                raise PermissionError("sharing fixture")
            return replace(source, destination)
        with patch.object(u.os, "replace", side_effect=sharing):
            u._write_json(path, {"state": "after"})
        self.assertEqual(len(calls), 2)
        self.assertEqual(u._read_json(path), {"state": "after"})

    def test_dirty_source_blocks_automatic_update_with_retained_explanation(self):
        service.configure(True, True, target=self.target)
        with patch.object(u, "_source_guard", side_effect=u.UpdateError("Modifications locales presentes")), \
             patch.object(service.subprocess, "Popen") as spawn:
            result = service.startup(self.target)
        self.assertFalse(result["ok"])
        self.assertIn("Modifications locales", service.status(target=self.target)["message"])
        self.assertEqual(service.status(target=self.target)["operation"]["state"], "launch_failed")
        spawn.assert_not_called()
        self.assertIsNone(self.target.state()["active"])


class UpdateProtocolTests(TemporaryInstallation):
    def test_real_stdio_model_visibility_and_persistent_authorization(self):
        from mcp import ClientSession, StdioServerParameters, stdio_client
        from romeo_mcp import __version__
        from romeo_mcp.profiles import ESSENTIAL_TOOLS
        from smoke_protocol import OUTILS_ATTENDUS
        env = {**os.environ, "PYTHONPATH": str(ROOT), "ROMEO_UPDATES_DIR": str(self.root / "protocol-updates"),
               "ROMEO_CONFIG": str(self.root / "unused-config.json"), "ROMEO_MCP_DB": str(self.root / "jobs.db"),
               "ROMEO_UPDATE_CHECK": "0", "ROMEO_AUTO_UPDATE": "0", u.ORIGIN_ENV: "", u.DISPATCH_ENV: ""}
        with patch.dict(os.environ, env):
            target = u.installation()
        u._write_json(target.root / "check.json", {"schema": 2, "checked_at": time.time(), "release": release(), "error": None})
        async def exercise():
            params = StdioServerParameters(command=sys.executable, args=["-m", "romeo_mcp", "serve", "--profile", "essential"], env=env, cwd=str(self.root))
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as client:
                    init = await client.initialize()
                    self.assertIn("mcp_update_check", init.instructions)
                    tools = (await client.list_tools()).tools
                    self.assertEqual({t.name for t in tools}, ESSENTIAL_TOOLS)
                    result = await client.call_tool("mcp_update_check", {})
                    value = json.loads(result.content[0].text)
                    self.assertTrue(value["update_available"])
                    self.assertEqual(value["running_version"], __version__)
                    self.assertEqual(value["latest_version"], "9.0.0")
                    result = await client.call_tool("mcp_update_start", {})
                    self.assertFalse(json.loads(result.content[0].text)["ok"])
                    result = await client.call_tool("mcp_update_policy", {"automatic": True, "confirm": True})
                    self.assertTrue(json.loads(result.content[0].text)["saved_automatic"])
                    result = await client.call_tool("mcp_update_status", {})
                    self.assertIsNone(json.loads(result.content[0].text)["operation"])
                    await client.call_tool("tool_profile_set", {"profile": "expert"})
                    self.assertEqual({t.name for t in (await client.list_tools()).tools}, OUTILS_ATTENDUS)
        asyncio.run(exercise())
        self.assertTrue(u._read_json(target.root / "policy.json")["automatic"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
