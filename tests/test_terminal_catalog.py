"""Global coverage, bounded pages, readonly evidence and private cache invalidation."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from romeo_mcp import terminal_catalog as catalog
from romeo_mcp.registry import _SCHEMA


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="romeo catalog ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / "jobs.db"
        self.environment = patch.dict(os.environ, {
            "ROMEO_CONFIG": str(self.root / "config.json"), "ROMEO_MCP_DB": str(self.path),
            "ROMEO_UPDATES_DIR": str(self.root / "updates"), "ROMEO_REPORTS_DIR": str(self.root / "reports"),
            "ROMEO_UPDATE_CHECK": "0", "ROMEO_AUTO_ISSUES": "0"})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.reader = catalog.Catalog(db=self.path)
        self.addCleanup(self.reader.close)

    def jobs(self, count=81):
        at = time.time()
        with closing(sqlite3.connect(self.path)) as db:
            db.executescript(_SCHEMA)
            for index in range(count):
                identifier = str(index + 1)
                state = "RUNNING" if index == 0 else "FAILED" if index == 1 else "COMPLETED"
                db.execute("INSERT INTO jobs(job_id,name,partition,submitted_at,last_state,script) VALUES(?,?,?,?,?,?)",
                           (identifier, "Ancien calcul actif" if index == 0 else "Prétraitement " + identifier,
                            "cpu", at - count + index, state,
                            "#SBATCH --nodes=2\n#SBATCH --ntasks-per-node=4\n#SBATCH --cpus-per-task=8\n"
                            "#SBATCH --gpus-per-task=1\nexport OMP_NUM_THREADS=8\nsecret-script-do-not-export"))
                payload = {"job_id": identifier, "ok": True, "state": state,
                           "nodes": "2", "result_validated": state == "COMPLETED"}
                db.execute("INSERT INTO job_observations VALUES(?,?,?,?)",
                           (identifier, '{"host":"secret-target"}', at - 10, json.dumps(payload)))
            db.commit()

    def transfer(self, identifier=0, *, verified=False):
        path = self.root / "transfers" / f"{identifier:032x}"
        path.mkdir(parents=True, exist_ok=True)
        plan = {"id": path.name, "direction": "download", "local_path": f"result-{identifier}.bin",
                "remote_path": f"synthetic/result-{identifier}.bin", "recursive": False,
                "verify": True, "target": {"host": "secret-target"}, "created_at": time.time() - 60}
        plan["sha256"] = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
        (path / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        status = {"transfer_id": path.name, "state": "completed", "heartbeat_at": time.time() - 10,
                  "ok": True, "result_validated": verified}
        (path / "status.json").write_text(json.dumps(status), encoding="utf-8")
        return path, status

    def test_old_active_job_is_in_first_page_and_search_covers_entire_registry(self):
        self.jobs()
        result = self.reader.snapshot()
        self.assertEqual(result["schema"], 3)
        self.assertEqual(result["coverage"]["jobs"],
                         {"page": 0, "pages": 3, "loaded": 40, "matched": 81, "total": 81, "page_size": 40})
        self.assertEqual(result["jobs"][0]["id"], "1")
        found = self.reader.snapshot({"queries": {"jobs": "PRETRAITEMENT 2"}})
        self.assertTrue(any(row["id"] == "2" for row in found["jobs"]))
        self.assertEqual(found["coverage"]["jobs"]["total"], 81)
        self.assertEqual(len(self.reader.snapshot({"queries": {"jobs": "en cours"}})["jobs"]), 1)
        self.assertEqual(self.reader.snapshot({"queries": {"jobs": "%' OR 1=1"}})["jobs"], [])

    def test_pages_are_disjoint_clamped_and_alerts_ignore_job_filter(self):
        self.jobs()
        first = self.reader.snapshot({"sorts": {"jobs": "date"}})
        second = self.reader.snapshot({"sorts": {"jobs": "date"}, "pages": {"jobs": 1}})
        last = self.reader.snapshot({"sorts": {"jobs": "date"}, "pages": {"jobs": 99}})
        identifiers = [row["id"] for result in (first, second, last) for row in result["jobs"]]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertEqual(len(identifiers), 81)
        self.assertEqual(last["coverage"]["jobs"]["page"], 2)
        empty = self.reader.snapshot({"queries": {"jobs": "no matching job"}})
        self.assertEqual(empty["jobs"], [])
        self.assertEqual(empty["attention"][0]["id"], "2")
        self.assertEqual(empty["coverage"]["alerts"]["total"], 1)

    def test_warm_job_cache_skips_reads_and_wal_changes_invalidate_it(self):
        self.jobs()
        self.reader.snapshot()
        with patch.object(catalog.data, "iter_jobs", side_effect=AssertionError("unchanged DB read")):
            self.reader.snapshot({"queries": {"jobs": "termine"}})
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("UPDATE jobs SET name='Changed by writer' WHERE job_id='1'")
            db.commit()
            result = self.reader.snapshot({"queries": {"jobs": "Changed by writer"}})
            self.assertEqual(result["jobs"][0]["id"], "1")
        before = self.reader.job_reads
        self.reader.snapshot({"force": True})
        self.assertEqual(self.reader.job_reads, before + 1)

    def test_hpc_counts_have_sources_and_never_export_script_or_target(self):
        self.jobs(3)
        original = self.path.read_bytes()
        result = self.reader.snapshot()
        resources = result["jobs"][0]["resources"]
        self.assertEqual(resources["requested"], {"nodes": 2, "tasks_per_node": 4,
                         "cpus_per_task": 8, "gpus_per_task": 1, "omp_threads": 8})
        self.assertEqual(resources["observed"], {"nodes": 2})
        self.assertNotIn("secret-", json.dumps(result))
        self.assertEqual(self.path.read_bytes(), original)

    def test_missing_source_retains_previous_jobs_then_recovers(self):
        self.jobs(3)
        self.reader.snapshot()
        backup = self.path.with_suffix(".backup")
        self.path.rename(backup)
        failed = self.reader.snapshot()
        self.assertEqual(len(failed["jobs"]), 3)
        self.assertTrue(failed["warnings"])
        self.assertEqual(len(self.reader.snapshot()["jobs"]), 3)
        backup.rename(self.path)
        self.assertFalse(self.reader.snapshot()["warnings"])

    def test_transfer_cache_skips_json_reads_but_observes_validation_changes(self):
        path, status = self.transfer()
        first = self.reader.snapshot()
        self.assertEqual(first["coverage"]["alerts"]["total"], 1)
        counts = self.reader.files.reads, self.reader.files.scans
        second = self.reader.snapshot({"queries": {"transfers": "termine"}})
        self.assertEqual(second["coverage"]["transfers"]["matched"], 1)
        self.assertEqual((self.reader.files.reads, self.reader.files.scans), counts)
        status["result_validated"] = True
        (path / "status.json").write_text(json.dumps(status), encoding="utf-8")
        verified = self.reader.snapshot()
        self.assertTrue(verified["transfers"][0]["result_validated"])
        self.assertEqual(verified["coverage"]["alerts"]["total"], 0)
        plan = json.loads((path / "plan.json").read_text(encoding="utf-8"))
        plan["local_path"] = "corrupted-plan"
        (path / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        corrupted = self.reader.snapshot()
        self.assertEqual(corrupted["transfers"], [])
        self.assertTrue(corrupted["warnings"])

    def test_transfers_beyond_previous_thousand_directory_limit_are_searchable(self):
        for index in range(1002):
            self.transfer(index, verified=True)
        result = self.reader.snapshot({"queries": {"transfers": "result-1001.bin"}})
        self.assertEqual(result["coverage"]["transfers"]["total"], 1002)
        self.assertEqual(result["transfers"][0]["id"], f"{1001:032x}")
        self.assertFalse(result["warnings"])

    def test_freshness_thresholds_are_independent_and_future_is_an_alert(self):
        self.jobs(3)
        path, status = self.transfer(verified=True)
        status.update(state="running", heartbeat_at=time.time() - 90)
        (path / "status.json").write_text(json.dumps(status), encoding="utf-8")
        result = self.reader.snapshot({"job_stale_after": 300, "transfer_stale_after": 60})
        self.assertEqual(result["coverage"]["alerts"]["total"], 2)
        relaxed = self.reader.snapshot({"job_stale_after": 300, "transfer_stale_after": 120})
        self.assertEqual(relaxed["coverage"]["alerts"]["total"], 1)
        status["heartbeat_at"] = time.time() + 3600
        (path / "status.json").write_text(json.dumps(status), encoding="utf-8")
        self.assertEqual(self.reader.snapshot()["coverage"]["alerts"]["total"], 2)

    def test_one_changed_transfer_does_not_reparse_other_plans(self):
        self.transfer(1, verified=True)
        path, status = self.transfer(2)
        self.reader.snapshot()
        self.reader.files.clear()
        status["result_validated"] = True
        (path / "status.json").write_text(json.dumps(status), encoding="utf-8")
        with patch.object(catalog.data, "read_transfer", wraps=catalog.data.read_transfer) as read:
            self.reader.snapshot()
            self.assertEqual(read.call_count, 1)
            self.assertEqual(read.call_args.args[0], path)

    def test_selected_identity_is_anchored_across_global_sort_and_refresh(self):
        self.jobs()
        for sort in ("activity", "date", "state", "priority"):
            result = self.reader.snapshot({"sorts": {"jobs": sort}, "anchors": {"jobs": "1"}})
            self.assertIn("1", [job["id"] for job in result["jobs"]])
        self.assertEqual(self.reader.snapshot({"queries": {"jobs": "recent"}})["coverage"]["jobs"]["matched"], 81)
        self.assertEqual(self.reader.snapshot({"queries": {"jobs": "ancien"}})["coverage"]["jobs"]["matched"], 1)
        self.assertEqual(self.reader.snapshot({"queries": {"jobs": "ancien"}, "job_stale_after": 1})["coverage"]["jobs"]["matched"], 81)

    def test_cache_bytes_are_bounded_and_progress_never_contains_private_ids(self):
        from romeo_mcp.terminal_cache import JsonFiles
        path = self.root / "cache.json"
        path.write_text('{"value":"' + "a" * 200 + '"}', encoding="utf-8")
        cache = JsonFiles(byte_limit=100)
        cache.read(path)
        self.assertEqual(cache.bytes, 0)
        self.assertEqual(len(cache.files), 0)
        self.jobs(3)
        messages = []
        self.reader.progress = messages.append
        with patch.object(catalog.time, "monotonic", side_effect=range(100)):
            result = self.reader.snapshot({"request_id": 7})
        self.assertTrue(messages)
        self.assertTrue(all(message["request_id"] == result["request_id"] for message in messages))
        self.assertNotIn("secret", json.dumps(messages))

    def test_demo_never_opens_user_registry_or_report_files(self):
        demo = catalog.Catalog(demo=True)
        self.addCleanup(demo.close)
        with patch.object(catalog.data, "registry_path", side_effect=AssertionError("private files")), \
                patch.object(catalog.data, "read_json", side_effect=AssertionError("private files")):
            result = demo.snapshot({"request_id": 42, "queries": {"transfers": "a verifier"}})
        self.assertEqual(result["request_id"], 42)
        self.assertTrue(result["demo"])
        self.assertEqual(len(result["transfers"]), 1)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_invalid_requests_are_rejected_before_any_source_read(self):
        for invalid in ({"unknown": 1}, {"pages": {"jobs": True}}, {"force": "true"},
                        {"queries": {"jobs": "x" * 81}}, {"queries": {"jobs": "\x1b"}},
                        {"sorts": {"jobs": "SQL injection"}}, {"job_stale_after": 0},
                        {"request_id": 2**54}, {"pages": {"private": 1}}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.reader.snapshot(invalid)
        self.assertEqual(list(self.root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
