"""Rapports publics : consentement, confidentialite et effets GitHub simules."""
from __future__ import annotations

import asyncio
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from romeo_mcp import issue_github as github, issue_reports as reports
from romeo_mcp.issue_store import ReportStore
from romeo_mcp.updates import REPOSITORY


def sample(**changes):
    return {"tool_name": "job_prepare", "summary": "Plan incomplet apres validation",
            "observed": "Le plan valide omet une option demandee.",
            "expected": "Le plan conserve toutes les options validees.",
            "steps": ["Preparer un exemple minimal fictif.", "Relire le plan."], **changes}


class FakeGitHub:
    def __init__(self):
        self.calls = []
        self.existing = None
        self.issue = None
        self.find_error = None
        self.create_error = None
        self.get_error = None

    def find(self, digest):
        self.calls.append("find")
        if self.find_error:
            raise self.find_error
        return self.existing

    def create(self, title, body, digest):
        self.calls.append("create")
        if self.create_error:
            raise self.create_error
        self.issue = {"number": 41, "url": f"https://github.com/{REPOSITORY}/issues/41",
                      "title": title, "body": body, "state": "open"}
        return self.issue

    def get(self, number, digest):
        self.calls.append("get")
        if self.get_error:
            raise self.get_error
        return self.issue


class ReportFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="romeo reports ")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("ROMEO_")}
        self.env.update(ROMEO_CONFIG=str(self.root / "config.json"), ROMEO_REPORTS_DIR=str(self.root / "reports"),
                        ROMEO_MCP_DB=str(self.root / "jobs.db"), ROMEO_UPDATE_CHECK="0", ROMEO_AUTO_UPDATE="0",
                        PYTHONPATH=str(ROOT), PYTHONIOENCODING="utf-8")
        env_patch = patch.dict(os.environ, self.env, clear=True)
        env_patch.start()
        self.addCleanup(env_patch.stop)
        self.store = ReportStore()
        self.fake = FakeGitHub()

    def local(self, **changes):
        return reports.report(**sample(**changes), store=self.store)

    def authorize(self):
        return reports.policy_set(True, True, store=self.store)

    def publish(self, report_id, **kwargs):
        return reports.publish(report_id, store=self.store, client=self.fake, **kwargs)

    def existing_issue(self, record, number=41, state="open"):
        title, body = reports.render(record["status"])
        return {"number": number, "url": f"https://github.com/{REPOSITORY}/issues/{number}",
                "state": state, "title": title, "body": body}

    def expire_backoff(self, report_id):
        current = self.store.get(report_id)
        self.store.update(report_id, current["state"], issue_number=current["issue_number"],
                          issue_url=current["issue_url"], last_error=current["last_error"])


class ReportTests(ReportFixture):
    def test_default_has_no_collection_network_or_created_database(self):
        with patch.object(reports, "GitHubClient") as network:
            self.assertFalse(reports.policy_get(store=self.store)["automatic_enabled"])
            self.assertEqual(reports.status(store=self.store)["reports"], [])
            self.assertFalse(self.store.root.exists())
            record = self.local()
        network.assert_not_called()
        self.assertFalse(record["published"])
        self.assertEqual(record["status"]["state"], "local_only")
        self.assertFalse((self.root / "jobs.db").exists())

    def test_authorization_survives_reconnection_and_environment_override(self):
        with self.assertRaisesRegex(ValueError, "confirm=true"):
            reports.policy_set(True, store=self.store)
        self.authorize()
        self.assertTrue(reports.policy_get(store=ReportStore())["automatic_enabled"])
        with patch.dict(os.environ, ROMEO_AUTO_ISSUES="0"):
            policy = reports.policy_get(store=self.store)
            self.assertFalse(policy["automatic_enabled"])
            self.assertTrue(policy["saved_automatic"])
        reports.policy_set(False, store=self.store)
        with patch.dict(os.environ, ROMEO_AUTO_ISSUES="1"):
            self.assertTrue(reports.policy_get(store=self.store)["automatic_enabled"])
        with patch.dict(os.environ, ROMEO_AUTO_ISSUES="invalid"):
            with self.assertRaises(ValueError):
                reports.policy_get(store=self.store)

    def test_automatic_report_without_gh_or_login_remains_local_without_http(self):
        for executable in (None, "gh"):
            with self.subTest(gh=executable), \
                 patch.object(github, "gh_executable", return_value=executable), \
                 patch.object(github.subprocess, "run", return_value=SimpleNamespace(
                     returncode=1, stdout="", stderr="synthetic-private-auth-error")), \
                 patch.object(github, "build_opener") as network:
                self.authorize()
                result = reports.report(**sample(summary=f"Diagnostic sans connexion {executable}"), store=self.store)
                self.assertFalse(result["published"])
                self.assertEqual(result["status"]["state"], "failed")
                self.assertEqual(result["status"]["last_error"], "github_authentication_missing")
                self.assertIsNone(result["issue_url"])
                self.assertEqual(result["status"]["attempts"], 0)
                self.assertNotIn("synthetic-private-auth-error", json.dumps(result))
                self.assertEqual(reports.status(result["report_id"], store=ReportStore())["status"]["state"], "failed")
                network.assert_not_called()

    def test_publication_requires_permission_before_any_network(self):
        record = self.local()
        with self.assertRaisesRegex(ValueError, "confirm=true"):
            self.publish(record["report_id"])
        self.assertEqual(self.fake.calls, [])
        self.assertTrue(self.publish(record["report_id"], confirm=True)["created"])
        self.assertFalse(reports.policy_get(store=self.store)["automatic_enabled"])

    def test_automatic_report_is_created_then_observed_and_not_reposted(self):
        self.authorize()
        with patch.object(reports, "GitHubClient", return_value=self.fake):
            first = self.local()
            again = self.local()
        self.assertEqual(self.fake.calls, ["find", "create", "get"])
        self.assertTrue(first["created"])
        self.assertTrue(first["result_validated"])
        self.assertFalse(again["created"])
        self.assertEqual(again["status"]["occurrences"], 2)
        self.assertEqual(again["status"]["attempts"], 1)
        self.assertTrue(reports.status(first["report_id"], store=ReportStore())["published"])

    def test_existing_closed_issue_is_a_duplicate_not_a_new_creation(self):
        record = self.local()
        self.fake.existing = self.existing_issue(record, 12, "closed")
        result = self.publish(record["report_id"], confirm=True)
        self.assertEqual(self.fake.calls, ["find"])
        self.assertEqual(result["status"]["state"], "duplicate")
        self.assertTrue(result["published"])
        self.assertFalse(result["created"])

    def test_found_issue_with_changed_title_or_body_is_not_validated_or_reposted(self):
        for field in ("title", "body"):
            with self.subTest(field=field):
                record = self.local(summary=f"Defaut fictif dans {field}")
                self.fake.calls.clear()
                original = self.existing_issue(record, 12)
                self.fake.existing = {**original, field: original[field] + " modified"}
                result = self.publish(record["report_id"], confirm=True)
                self.assertFalse(result["result_validated"])
                self.assertEqual(result["status"]["state"], "publication_unknown")
                self.assertEqual(result["status"]["issue_number"], 12)
                self.assertEqual(result["status"]["last_error"], "github_issue_content_mismatch")
                self.assertEqual(self.fake.calls, ["find"])
                self.expire_backoff(record["report_id"])
                self.fake.issue = self.fake.existing
                resumed = self.publish(record["report_id"], confirm=True)
                self.assertFalse(resumed["result_validated"])
                self.assertEqual(self.fake.calls, ["find", "get"])
                self.expire_backoff(record["report_id"])
                self.fake.issue = original
                reconciled = self.publish(record["report_id"], confirm=True)
                self.assertTrue(reconciled["result_validated"])
                self.assertEqual(self.fake.calls, ["find", "get", "get"])

    def test_private_values_are_removed_before_storage_and_http(self):
        credential = "ghp_" + "a" * 36
        with patch.dict(os.environ, ROMEO_ACCOUNT="private-project-alpha", ROMEO_HOST="private-login-host",
                        ROMEO_GITHUB_TOKEN=credential), \
             patch.object(reports, "GitHubClient", return_value=self.fake):
            self.authorize()
            result = self.local(observed=("Echec technique apres private-project-alpha sur private-login-host.\n"
                                          f"Copie {credential} puis /scratch_p/person/dataset.csv et C:\\Users\\person\\run.log.\n"
                                          "Contact person@example.org, IP 192.0.2.41 et job 123456.\n"
                                          "Reference https://example.org/private?key=secret et @someone.\n"))
        serialized = json.dumps(result) + self.fake.issue["body"]
        for private in (credential, "private-project-alpha", "private-login-host", "dataset.csv", "person@example.org",
                        "192.0.2.41", "123456", "@someone", "example.org", "run.log"):
            self.assertNotIn(private, serialized)
        self.assertIn("Echec technique", serialized)
        self.assertTrue(result["status"]["report"]["redaction_applied"])
        with closing(sqlite3.connect(self.store.path)) as db:
            raw = db.execute("SELECT document FROM reports").fetchone()[0]
        self.assertNotIn(credential, raw)
        self.assertNotIn("private-project-alpha", raw)

    def test_private_key_multiline_control_and_markdown_are_filtered(self):
        private = "-----BEGIN " + "PRIVATE KEY-----\nopaque-private-material\n-----END " + "PRIVATE KEY-----"
        result = self.local(observed="Symptome observe.\n" + private + "\n\x1b[31m\u202e texte @person", steps=["```\n<img src='x'>\n```"])
        _, body = reports.render(result["status"])
        self.assertNotIn("opaque-private-material", body)
        self.assertNotIn("\x1b", body)
        self.assertNotIn("\u202e", body)
        self.assertNotIn("@person", body)
        self.assertNotIn("<img", body)

    def test_invalid_or_oversized_reports_do_not_write_or_connect(self):
        for changes in ({"summary": "x" * 161}, {"steps": "not-a-list"}, {"steps": ["x"] * 9},
                        {"category": "other"}, {"observed": ""}, {"tool_name": "mcp_issue_report"},
                        {"tool_name": "private_person_name"},
                        {"error_code": "contains spaces"}):
            with self.assertRaises(ValueError), patch.object(reports, "GitHubClient") as client:
                self.local(**changes)
            client.assert_not_called()
        self.assertFalse(self.store.path.exists())

    def test_unrecognized_personal_prose_and_private_hash_never_leave_the_client(self):
        record = self.local(summary="Rapport pour Alice Exemple", observed="Alice Exemple habite une rue privee.",
                            expected="Attendu pour une personne privee", steps=["Dossier personnel confidentiel"],
                            error_code="PRIVATE_USER_CODE", diagnostic="incorrect_measurement")
        result = self.publish(record["report_id"], confirm=True)
        wire = self.fake.issue["title"] + self.fake.issue["body"]
        for private in ("Alice", "rue privee", "personne privee", "Dossier personnel", "PRIVATE_USER_CODE",
                        record["status"]["fingerprint"], record["report_id"]):
            self.assertNotIn(private, wire)
        self.assertIn("Mesure ou calcul incorrect", wire)
        self.assertTrue(result["published"])

    def test_public_deduplication_excludes_private_descriptions_and_os(self):
        from romeo_mcp import issue_public
        first = self.local(summary="Description technique A")
        second = self.local(summary="Description technique B")
        self.assertNotEqual(first["report_id"], second["report_id"])
        self.assertEqual(issue_public.digest(first["status"]["report"]), issue_public.digest(second["status"]["report"]))
        public = issue_public.projection(first["status"]["report"])
        self.assertNotIn("os", public["context"])
        self.assertEqual(set(public), {"schema", "tool_name", "category", "diagnostic", "context"})

    def test_unknown_tools_and_legacy_uncertain_reports_do_not_contact_github(self):
        from romeo_mcp import issue_public
        doc = reports.document(**sample())
        doc["tool_name"] = "private_person_name"
        with self.assertRaises(ValueError):
            issue_public.projection(doc)
        doc = reports.document(**sample())
        doc.pop("publication_schema")
        record = self.store.save(doc)
        self.store.update(record["report_id"], "publishing")
        result = self.publish(record["report_id"], confirm=True)
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"]["state"], "publication_unknown")
        self.assertEqual(self.fake.calls, [])

    def test_local_erasure_keeps_consent_and_rate_limits_and_does_not_call_github(self):
        first = self.local()
        self.store.configure(True)
        self.store.start_attempt(first["report_id"])
        self.assertEqual(self.store.delete_local(first["report_id"]), 1)
        self.assertTrue(self.store.policy()["saved_automatic"])
        self.assertEqual(self.store.recent(), [])
        with closing(sqlite3.connect(self.store.path)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT report_id FROM attempts").fetchone()[0], "")
        self.assertEqual(self.fake.calls, [])

    def test_uncertain_post_is_reconciled_without_a_second_post(self):
        record = self.local()
        self.fake.create_error = github.GitHubError("github_connection_failed", uncertain=True)
        first = self.publish(record["report_id"], confirm=True)
        self.assertEqual(first["status"]["state"], "publication_unknown")
        self.assertFalse(first["published"])
        self.fake.create_error = None
        self.expire_backoff(record["report_id"])
        again = self.publish(record["report_id"], confirm=True)
        self.assertEqual(again["status"]["state"], "publication_unknown")
        self.assertEqual(self.fake.calls.count("create"), 1)
        self.fake.existing = self.existing_issue(record)
        recovered = self.publish(record["report_id"], confirm=True)
        self.assertTrue(recovered["result_validated"])
        self.assertEqual(self.fake.calls.count("create"), 1)

    def test_process_interrupted_after_post_intent_never_reposts(self):
        record = self.local()
        self.store.start_attempt(record["report_id"])
        result = self.publish(record["report_id"], confirm=True)
        self.assertEqual(result["status"]["state"], "publication_unknown")
        self.assertEqual(self.fake.calls, ["find"])

    def test_created_but_unobserved_issue_keeps_its_number_after_reconnection(self):
        record = self.local()
        self.fake.get_error = github.GitHubError("github_connection_failed")
        first = self.publish(record["report_id"], confirm=True)
        self.assertFalse(first["published"])
        self.assertEqual(first["status"]["issue_number"], 41)
        self.fake.get_error = None
        self.expire_backoff(record["report_id"])
        recovered = self.publish(record["report_id"], confirm=True)
        self.assertTrue(recovered["published"])
        self.assertEqual(self.fake.calls.count("create"), 1)
        self.assertEqual(self.fake.calls[-1], "get")

    def test_changed_remote_body_cannot_be_announced_as_verified(self):
        record = self.local()
        actual_get = self.fake.get
        def altered(number, digest):
            return {**actual_get(number, digest), "body": "different body"}
        with patch.object(self.fake, "get", side_effect=altered):
            first = self.publish(record["report_id"], confirm=True)
            self.expire_backoff(record["report_id"])
            second = self.publish(record["report_id"], confirm=True)
        self.assertFalse(first["result_validated"])
        self.assertFalse(second["result_validated"])
        self.assertEqual(second["status"]["state"], "publication_unknown")
        self.assertEqual(self.fake.calls.count("create"), 1)

    def test_known_http_refusal_is_not_ambiguous_and_backoff_prevents_requests(self):
        record = self.local()
        self.fake.create_error = github.GitHubError("github_http_422")
        first = self.publish(record["report_id"], confirm=True)
        self.assertEqual(first["status"]["state"], "failed")
        calls = self.fake.calls[:]
        second = self.publish(record["report_id"], confirm=True)
        self.assertEqual(self.fake.calls, calls)
        self.assertGreater(second["retry_after"], 0)
        self.assertFalse(second["published"])

    def test_github_throttle_applies_to_other_reports_after_reconnection(self):
        first = self.local()
        self.fake.find_error = github.GitHubError("github_http_429", retry_seconds=600)
        self.publish(first["report_id"], confirm=True)
        second = self.local(summary="Autre defaut observe")
        result = self.publish(second["report_id"], confirm=True)
        self.assertEqual(self.fake.calls, ["find"])
        self.assertEqual(result["status"]["state"], "rate_limited")
        self.assertGreater(result["retry_after"], 0)

    def test_rate_limit_is_shared_across_reports_and_uses_a_rolling_day(self):
        start = 2_000_000_000.0
        with patch("time.time", return_value=start) as clock:
            for index in range(5):
                clock.return_value = start + index * 61
                record = self.local(summary=f"Defaut fictif {index}")
                self.assertTrue(self.publish(record["report_id"], confirm=True)["created"])
            clock.return_value = start + 305
            record = self.local(summary="Sixieme defaut fictif")
            limited = self.publish(record["report_id"], confirm=True)
            self.assertEqual(limited["status"]["state"], "rate_limited")
            self.assertEqual(self.fake.calls.count("create"), 5)
            clock.return_value = start + 86401
            self.assertTrue(self.publish(record["report_id"], confirm=True)["created"])

    def test_minimum_interval_does_not_block_finding_an_existing_duplicate(self):
        first = self.local()
        self.publish(first["report_id"], confirm=True)
        second = self.local(summary="Autre defaut observe")
        limited = self.publish(second["report_id"], confirm=True)
        self.assertEqual(limited["status"]["state"], "rate_limited")
        self.assertEqual(self.fake.calls.count("create"), 1)
        third = self.local(summary="Defaut deja signale ailleurs")
        self.fake.existing = self.existing_issue(third)
        self.assertTrue(self.publish(third["report_id"], confirm=True)["published"])
        self.assertEqual(self.fake.calls.count("create"), 1)

    def test_publication_lock_prevents_concurrent_post_and_releases_cleanly(self):
        record = self.local()
        with self.store.publication_lock(), ThreadPoolExecutor(1) as workers:
            result = workers.submit(self.publish, record["report_id"], confirm=True)
            with self.assertRaisesRegex(ValueError, "deja en cours"):
                result.result(timeout=3)
        self.assertEqual(self.fake.calls, [])
        self.assertTrue(self.publish(record["report_id"], confirm=True)["created"])

    def test_revocation_during_remote_lookup_prevents_new_post(self):
        record = self.local()
        self.authorize()
        def revoke(digest):
            reports.policy_set(False, store=self.store)
            return None
        with patch.object(self.fake, "find", side_effect=revoke):
            result = self.publish(record["report_id"])
        self.assertFalse(result["published"])
        self.assertNotIn("create", self.fake.calls)

    def test_tampered_report_cannot_publish_and_repo_storage_is_forbidden(self):
        record = self.local()
        with closing(sqlite3.connect(self.store.path)) as db, db:
            doc = json.loads(db.execute("SELECT document FROM reports").fetchone()[0])
            doc["observed"] = "altered local content"
            db.execute("UPDATE reports SET document=?", (json.dumps(doc),))
        with self.assertRaisesRegex(ValueError, "altere"):
            self.publish(record["report_id"], confirm=True)
        self.assertEqual(self.fake.calls, [])
        with self.assertRaisesRegex(ValueError, "hors des depots"):
            ReportStore(ROOT / "test-issue-reports")
        for report_id in ("../private", "a" * 33, "", "z" * 32):
            with self.assertRaises(ValueError):
                reports.status(report_id or "invalid", store=self.store)

    def test_cli_consent_and_status_are_local_from_an_unrelated_directory(self):
        def cli(*args):
            return subprocess.run([sys.executable, "-m", "romeo_mcp", "issues", *args],
                                  cwd=self.root, env=self.env, capture_output=True, text=True, timeout=15)
        default = cli()
        self.assertEqual(default.returncode, 0, default.stderr)
        self.assertFalse(json.loads(default.stdout)["policy"]["automatic_enabled"])
        denied = cli("--enable-automatic")
        self.assertNotEqual(denied.returncode, 0)
        self.assertIn("confirm=true", denied.stderr)
        enabled = cli("--enable-automatic", "--yes")
        self.assertTrue(json.loads(enabled.stdout)["automatic_enabled"])
        disabled = cli("--disable-automatic")
        self.assertFalse(json.loads(disabled.stdout)["automatic_enabled"])

    def test_cli_local_erasure_requires_confirmation_and_respects_the_selected_report(self):
        def cli(*args):
            return subprocess.run([sys.executable, "-m", "romeo_mcp", "issues", *args],
                                  cwd=self.root, env=self.env, capture_output=True, text=True, timeout=15)
        first = self.local()
        second = self.local(summary="Autre incident fictif")
        refused = cli("--delete-local", "--report-id", first["report_id"])
        self.assertNotEqual(refused.returncode, 0)
        self.assertEqual(len(self.store.recent()), 2)
        deleted = cli("--delete-local", "--report-id", first["report_id"], "--yes")
        self.assertEqual(deleted.returncode, 0, deleted.stderr)
        self.assertEqual(json.loads(deleted.stdout), {"ok": True, "deleted_local": 1, "github_issues_deleted": False})
        self.assertEqual(self.store.recent()[0]["report_id"], second["report_id"])
        all_deleted = cli("--delete-local", "--yes")
        self.assertEqual(all_deleted.returncode, 0, all_deleted.stderr)
        self.assertEqual(self.store.recent(), [])
        self.assertEqual(self.fake.calls, [])


class GitHubBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.credential = "ghp_" + "z" * 36
        patcher = patch.dict(os.environ, ROMEO_GITHUB_TOKEN=self.credential)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = github.GitHubClient()
        self.digest = "a" * 64

    def raw_issue(self, **changes):
        return {"number": 41, "html_url": f"https://github.com/{REPOSITORY}/issues/41",
                "title": "technical report", "body": github.marker(self.digest), "state": "open", **changes}

    def test_http_uses_fixed_host_headers_json_body_and_no_redirect(self):
        response = io.BytesIO(json.dumps(self.raw_issue()).encode())
        response.status = 201
        opener = Mock()
        opener.open.return_value = response
        with patch.object(github, "build_opener", return_value=opener) as factory:
            self.client.create("technical report", github.marker(self.digest), self.digest)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, github.API_ROOT + github.ENDPOINT)
        self.assertEqual(request.method, "POST")
        self.assertEqual(json.loads(request.data), {"title": "technical report", "body": github.marker(self.digest)})
        self.assertEqual(request.headers["Authorization"], "Bearer " + self.credential)
        self.assertIsInstance(factory.call_args.args[0], github.NoRedirect)
        self.assertIsNone(github.NoRedirect().redirect_request(None, None, 302, "", {}, "https://foreign.invalid"))

    def test_no_arbitrary_destination_or_mutation_is_exposed(self):
        for endpoint in ("https://foreign.invalid", "/repos/other/project/issues", github.ENDPOINT + "/../tokens"):
            with self.assertRaises(github.GitHubError), patch.object(github, "build_opener") as opener:
                self.client.request("POST", endpoint, {})
            opener.assert_not_called()
        with self.assertRaises(github.GitHubError):
            self.client.request("DELETE", github.ENDPOINT)

    def test_post_timeout_is_uncertain_and_error_contains_no_secret(self):
        opener = Mock()
        opener.open.side_effect = URLError(self.credential)
        with patch.object(github, "build_opener", return_value=opener):
            with self.assertRaises(github.GitHubError) as caught:
                self.client.create("technical report", github.marker(self.digest), self.digest)
        self.assertTrue(caught.exception.uncertain)
        self.assertNotIn(self.credential, str(caught.exception))

    def test_http_error_retry_after_and_auth_refusal_are_explicit(self):
        for code, expected_uncertain in ((401, False), (429, False), (503, True), (302, True)):
            opener = Mock()
            opener.open.side_effect = HTTPError(github.API_ROOT, code, self.credential, {"Retry-After": "600"}, None)
            with patch.object(github, "build_opener", return_value=opener), self.assertRaises(github.GitHubError) as caught:
                self.client.request("POST", github.ENDPOINT, {})
            self.assertEqual(caught.exception.uncertain, expected_uncertain)
            self.assertEqual(caught.exception.retry_seconds, 600)
            self.assertNotIn(self.credential, str(caught.exception))
        self.assertEqual(github.GitHubError("github_http_429", retry_seconds=172800).retry_seconds, 172800)

    def test_pagination_checks_closed_issues_and_ignores_pull_requests(self):
        pull_request = self.raw_issue(pull_request={"url": "unused"})
        with patch.object(self.client, "request", side_effect=[[pull_request] * 100, [self.raw_issue(state="closed")]]) as request:
            result = self.client.find(self.digest)
        self.assertEqual(result["state"], "closed")
        self.assertEqual(request.call_count, 2)
        self.assertIn("page=2", request.call_args.args[1])
        with patch.object(self.client, "request", return_value=[{"body": "unrelated"}] * 100):
            with self.assertRaisesRegex(github.GitHubError, "lookup_limit"):
                self.client.find(self.digest)

    def test_foreign_issue_missing_marker_or_invalid_response_are_not_success(self):
        for change in ({"html_url": "https://github.com/other/project/issues/41"}, {"body": "no marker"},
                       {"number": True}, {"state": "invented"}, {"pull_request": {}}):
            with patch.object(self.client, "request", return_value=self.raw_issue(**change)):
                with self.assertRaises(github.GitHubError) as caught:
                    self.client.create("technical report", "body", self.digest)
                self.assertTrue(caught.exception.uncertain)
        for value in (b"not-json", b"x" * (github.MAX_RESPONSE + 1)):
            with self.assertRaises(github.GitHubError) as caught:
                github._json(value, uncertain=True)
            self.assertTrue(caught.exception.uncertain)

    def test_gh_fallback_has_no_shell_secret_arguments_or_raw_error_export(self):
        response = io.BytesIO(json.dumps(self.raw_issue()).encode())
        response.status = 201
        opener = Mock()
        opener.open.return_value = response
        with patch.dict(os.environ, ROMEO_GITHUB_TOKEN="", ROMEO_ACCOUNT="private-project", GH_DEBUG="api"), \
             patch.object(github, "gh_executable", return_value="gh"), \
             patch.object(github, "build_opener", return_value=opener), \
             patch.object(github.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=self.credential + "\n", stderr="")) as run:
            client = github.GitHubClient()
            client.create("technical report", github.marker(self.digest), self.digest)
        args = run.call_args.args[0]
        options = run.call_args.kwargs
        self.assertEqual(args, ["gh", "auth", "token", "--hostname", "github.com"])
        self.assertNotIn(self.credential, " ".join(args))
        self.assertNotIn("ROMEO_ACCOUNT", options["env"])
        self.assertNotIn("GH_DEBUG", options["env"])
        self.assertNotIn("shell", options)
        self.assertEqual(options["stdin"], subprocess.DEVNULL)
        self.assertEqual(opener.open.call_args.args[0].headers["Authorization"], "Bearer " + self.credential)

    def test_bot_is_local_optional_and_personal_credentials_can_override_it(self):
        bot = "synthetic-bot-token"
        with patch.dict(os.environ, ROMEO_GITHUB_BOT_TOKEN=bot, ROMEO_ISSUE_ACCOUNT="auto", ROMEO_GITHUB_TOKEN=""):
            self.assertEqual(github.authentication()["method"], "bot_environment")
            self.assertEqual(github.GitHubClient()._token, bot)
            with patch.dict(os.environ, ROMEO_GITHUB_TOKEN=self.credential):
                self.assertEqual(github.authentication()["method"], "environment")
                self.assertEqual(github.GitHubClient()._token, self.credential)
            with patch.dict(os.environ, ROMEO_ISSUE_ACCOUNT="personal"), \
                 patch.object(github, "gh_executable", return_value="gh"), \
                 patch.object(github.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=self.credential, stderr="")):
                self.assertEqual(github.GitHubClient()._token, self.credential)

    def test_missing_bot_does_not_silently_use_the_personal_account(self):
        with patch.dict(os.environ, ROMEO_ISSUE_ACCOUNT="bot", ROMEO_GITHUB_BOT_TOKEN=""), \
             patch.object(github.subprocess, "run") as run:
            self.assertFalse(github.authentication()["configured"])
            with self.assertRaisesRegex(github.GitHubError, "authentication_missing"):
                github.GitHubClient()
            run.assert_not_called()

    def test_invalid_account_mode_is_refused_before_credentials_are_read(self):
        with patch.dict(os.environ, ROMEO_ISSUE_ACCOUNT="invalid"):
            with self.assertRaises(ValueError):
                github.GitHubClient()


class ProtocolTests(ReportFixture):
    def test_stdio_exposes_report_tools_in_essential_with_persistent_consent(self):
        from mcp import ClientSession, StdioServerParameters, stdio_client
        from romeo_mcp.profiles import ESSENTIAL_TOOLS
        from smoke_protocol import OUTILS_ATTENDUS
        names = {"mcp_issue_policy_get", "mcp_issue_policy_set", "mcp_issue_report", "mcp_issue_publish", "mcp_issue_status"}
        async def exercise():
            params = StdioServerParameters(command=sys.executable, args=["-m", "romeo_mcp", "serve", "--profile", "essential"],
                                           env=self.env, cwd=str(self.root))
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as client:
                    init = await client.initialize()
                    self.assertIn("mcp_issue_report", init.instructions)
                    tools = {t.name: t for t in (await client.list_tools()).tools}
                    self.assertEqual(set(tools), ESSENTIAL_TOOLS)
                    self.assertTrue(names <= set(tools))
                    self.assertTrue(tools["mcp_issue_status"].annotations.read_only_hint)
                    self.assertFalse(tools["mcp_issue_report"].annotations.read_only_hint)
                    self.assertTrue(tools["mcp_issue_report"].annotations.open_world_hint)
                    async def call(name, params):
                        value = await client.call_tool(name, params)
                        return json.loads(value.content[0].text)
                    disabled = await call("mcp_issue_policy_get", {})
                    self.assertFalse(disabled["automatic_enabled"])
                    denied = await call("mcp_issue_policy_set", {"automatic": True})
                    self.assertFalse(denied["ok"])
                    record = await call("mcp_issue_report", sample())
                    self.assertTrue(record["ok"])
                    self.assertFalse(record["published"])
                    denied = await call("mcp_issue_publish", {"report_id": record["report_id"]})
                    self.assertFalse(denied["ok"])
                    invalid = await call("mcp_issue_report", sample(tool_name="unknown_tool"))
                    self.assertFalse(invalid["ok"])
                    helper = await call("mcp_issue_report", sample(tool_name="main"))
                    self.assertFalse(helper["ok"])
                    enabled = await call("mcp_issue_policy_set", {"automatic": True, "confirm": True})
                    self.assertTrue(enabled["automatic_enabled"])
                    stored = await call("mcp_issue_status", {"report_id": record["report_id"]})
                    self.assertEqual(stored["report_id"], record["report_id"])
                    self.assertFalse(stored["published"])
                    caps = await call("romeo_capabilities", {"task": "issues"})
                    self.assertEqual({t["name"] for t in caps["groups"][0]["tools"]}, names)
                    await call("tool_profile_set", {"profile": "expert"})
                    self.assertEqual({t.name for t in (await client.list_tools()).tools}, OUTILS_ATTENDUS)
        asyncio.run(exercise())
        self.assertTrue(reports.policy_get(store=ReportStore())["automatic_enabled"])

    def test_unexpected_error_hint_does_not_copy_arguments_or_cause_report_loops(self):
        from romeo_mcp import server as assembled
        with patch.object(assembled.update_service, "check", side_effect=RuntimeError("private-fake-argument")):
            value = assembled.mcp_update_check()
        self.assertFalse(value["ok"])
        self.assertEqual(value["report_hint"]["tool_name"], "mcp_update_check")
        self.assertNotIn("private-fake-argument", json.dumps(value["report_hint"]))
        with patch.object(assembled.issue_reports, "policy_get", side_effect=RuntimeError("fixture")):
            self.assertNotIn("report_hint", assembled.mcp_issue_policy_get())
        with patch.object(assembled.update_service, "check", side_effect=ValueError("fixture")):
            self.assertNotIn("report_hint", assembled.mcp_update_check())


if __name__ == "__main__":
    unittest.main(verbosity=2)
