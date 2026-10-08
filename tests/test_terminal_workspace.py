"""Dossiers, global events, combined filters and sharing use only synthetic data."""
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

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from romeo_mcp.registry import Registry
from romeo_mcp.terminal_catalog import Catalog
from romeo_mcp.terminal_presentation import project
from romeo_mcp.terminal_remote import perform
from romeo_mcp.checkpoint_protocol import digest

TARGET={"host":"synthetic.example","user":"tester","account":"example"}


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory(prefix="romeo-ui-contract-"); self.addCleanup(folder.cleanup)
        self.root=Path(folder.name); self.path=self.root/"jobs.db"
        self.enterContext(patch.object(Path,"home",return_value=self.root))
        self.enterContext(patch.dict(os.environ,{"ROMEO_MCP_DB":str(self.path),"ROMEO_UPDATES_DIR":str(self.root/"updates"),
            "ROMEO_CONFIG":str(self.root/"config.json"),"ROMEO_REPORTS_DIR":str(self.root/"reports"),"ROMEO_AUTO_ISSUES":"0"}))
        self.enterContext(patch("romeo_mcp.terminal_data.config_path",return_value=self.root/"config.json"))
        self.store=Registry(self.path); self.addCleanup(self.store.close)

    def job(self,identifier="42",script="",state="RUNNING"):
        self.store.record(identifier,"private-project-name","gpu","x64cpu","/scratch/private","out","err",script)
        self.store.save_observation(identifier,TARGET,{"ok":True,"job_id":identifier,"state":state,"result_validated":False})

    def catalog(self,limit=40,progress=None):
        value=Catalog(db=self.path,limit=limit,progress=progress); self.addCleanup(value.close);return value

    def test_history_tracks_changes_not_elapsed_ticks_and_is_bounded(self):
        self.job(state="PENDING")
        self.store.save_observation("42",TARGET,{"ok":True,"job_id":"42","state":"PENDING","elapsed":"1"})
        self.store.save_observation("42",TARGET,{"ok":True,"job_id":"42","state":"PENDING","elapsed":"2"})
        self.store.save_observation("42",TARGET,{"ok":True,"job_id":"42","state":"RUNNING"})
        snapshot=self.catalog().snapshot()
        self.assertEqual([item["state"] for item in snapshot["workspace"]["events"]],["RUNNING","PENDING","PENDING"])
        for number in range(300):
            self.store.save_observation("42",TARGET,{"ok":True,"job_id":"42","state":"RUNNING" if number%2 else "PENDING"})
        count=self.store._conn.execute("SELECT COUNT(*) FROM observation_events WHERE job_id='42'").fetchone()[0]
        self.assertEqual(count,256)

    def test_search_only_does_not_collect_files_or_hide_global_completions(self):
        self.job("41");self.job("42")
        catalog=self.catalog(limit=1); catalog.snapshot()
        with patch.object(catalog,"_sync_transfers",side_effect=AssertionError("query must not collect")), patch.object(catalog,"_sync_jobs",side_effect=AssertionError("query must not collect")):
            value=catalog.snapshot({"collect":False,"queries":{"jobs":"41"}})
        self.assertEqual(value["jobs"][0]["id"],"41")
        self.store.save_observation("41",TARGET,{"ok":True,"job_id":"41","state":"COMPLETED","result_validated":False})
        value=catalog.snapshot()
        self.assertEqual(value["notifications"][0]["job_id"],"41")
        self.assertEqual(len(catalog.snapshot()["notifications"]),1)

    def test_combined_filters_are_global_accent_insensitive_and_parameterized(self):
        self.job("42","#SBATCH --gpus-per-node=1\n#SBATCH --cpus-per-task=8",state="COMPLETED")
        self.job("43",state="RUNNING")
        catalog=self.catalog(limit=1)
        result=catalog.snapshot({"queries":{"jobs":"etat:termine validation:check gpu:oui partition:gpu cpu:>=8"}})
        self.assertEqual(result["coverage"]["jobs"]["matched"],1)
        self.assertEqual(result["jobs"][0]["id"],"42")
        invalid=catalog.snapshot({"queries":{"jobs":"depuis:incorrect"},"collect":False})
        self.assertEqual(invalid["jobs"],[]);self.assertTrue(invalid["warnings"])
        injected=catalog.snapshot({"queries":{"jobs":"partition:\"gpu' OR 1=1--\""},"collect":False})
        self.assertEqual(injected["jobs"],[])
        self.assertEqual(catalog.snapshot({"collect":False})["coverage"]["jobs"]["total"],2)

    def test_partial_inventory_is_labelled_and_never_has_a_dossier_claim(self):
        self.job();messages=[];value=self.catalog(progress=messages.append).snapshot({"progressive":True})
        partial=next(message for message in messages if message.get("partial"))
        self.assertEqual(partial["jobs"][0]["id"],"42");self.assertEqual(partial["workspace"],{})
        self.assertFalse(value["partial"])

    def test_legacy_readers_receive_one_final_snapshot_without_unsolicited_partials(self):
        self.job()
        messages = []
        value = self.catalog(progress=messages.append).snapshot()
        self.assertFalse(value["partial"])
        self.assertTrue(all(item.get("message") == "progress" for item in messages))

    def test_dossier_has_only_explicit_links_and_records_unknown_gpu_usage(self):
        self.job();self.store.link_artifact("42","report","a"*32)
        self.store.save_observation("efficiency:42",TARGET,{"ok":True,"job_id":"42","alloc_gpus":1,"cpu_efficiency_pct":50,"max_rss_mb":None})
        self.store.save_observation("logs:42",TARGET,{"ok":True,"job_id":"42","stream":"err","content":"ordinary\napi_key=synthetic-private-value","truncated":False,"log_sha256":"x"})
        dossier=self.catalog().snapshot()["workspace"]
        self.assertEqual(len(dossier["links"]),1);self.assertEqual(dossier["links"][0]["basis"],"association explicite")
        self.assertIsNone(dossier["efficiency"]["gpu_utilization_pct"]);self.assertIsNone(dossier["efficiency"]["max_rss_mb"])
        self.assertNotIn("synthetic-private-value",dossier["logs"]["content"])

    def test_dossier_bounds_link_payload_and_keeps_known_total(self):
        self.job()
        for number in range(130):
            self.store.save_report({"job_id":"42","synthetic":number,"created_at":time.time()})
        dossier = self.catalog().snapshot()["workspace"]
        self.assertEqual(len(dossier["links"]),100)
        self.assertEqual(dossier["links_total"],130)

    def test_index_queries_reuse_metadata_and_keep_its_read_warnings(self):
        self.job()
        catalog = self.catalog()
        from romeo_mcp import terminal_data
        read_runtime = terminal_data.read_runtime

        def observed_runtime(path, warnings):
            warnings.append("Avertissement synthétique de métadonnées.")
            return read_runtime(path, warnings)

        with patch.object(terminal_data,"read_runtime",side_effect=observed_runtime):
            first = catalog.snapshot()
        with patch.object(terminal_data,"read_runtime",side_effect=AssertionError("query must not read runtime")), \
             patch.object(terminal_data,"read_updates",side_effect=AssertionError("query must not read updates")):
            queried = catalog.snapshot({"collect":False})
        self.assertIn("Avertissement synthétique de métadonnées.",first["warnings"])
        self.assertIn("Avertissement synthétique de métadonnées.",queried["warnings"])

    def test_history_records_changes_in_observed_remaining_dependencies(self):
        self.job(state="PENDING")
        for remaining in ("afterok:41","afterok:41",""):
            self.store.save_observation("42",TARGET,{"ok":True,"job_id":"42","state":"PENDING",
                "dependencies_remaining":remaining})
        payloads = [json.loads(row[0]) for row in self.store._conn.execute(
            "SELECT payload FROM observation_events WHERE job_id='42' ORDER BY event_id DESC")]
        self.assertEqual(len(payloads),3)
        self.assertEqual(payloads[0]["dependencies_remaining"],"")

    def test_checkpoint_proof_does_not_infer_backup_or_restart_from_a_file(self):
        self.job()
        latest={"generation":7,"step":12,"world_size":2,"run_id":"run","binding_sha256":"a"*64,"manifest_sha256":"b"*64,"integrity_verified":True}
        runtime={"schema":"romeo-runtime-observation-v1","job_id":"42","run_id":"run","world_size":2,"binding_sha256":"a"*64,
                 "latest_checkpoint":latest,"resume_validated":False,"observed_at":time.time()}
        self.store.save_observation("checkpoint:42",TARGET,runtime)
        recovery=self.catalog().snapshot()["workspace"]["recovery"]
        self.assertTrue(recovery["integrity"]);self.assertIsNone(recovery["independent_backup"]);self.assertFalse(recovery["resume_observed"])
        runtime["latest_checkpoint"]={**latest,"run_id":"another"}
        self.store.save_observation("checkpoint:42",TARGET,runtime)
        self.assertEqual(self.catalog().snapshot()["workspace"]["recovery"],{})

    def test_signed_pipeline_groups_actual_registered_children(self):
        self.job("42");self.job("43",state="FAILED")
        saved=self.store.prepare_submission({"kind":"pipeline","preview":{},"target":TARGET})
        self.store.update_submission(saved["plan_id"],"submitted",{"stages":[{"job_id":"42","stage":"prepare","depends_on":[]},
            {"job_id":"43","stage":"calculate","depends_on":["42"]}]})
        dossier=self.catalog().snapshot({"detail_job":"43"})["workspace"]
        self.assertEqual(dossier["group"]["dependencies"],"42");self.assertEqual(dossier["members"][1]["state"],"FAILED")
        self.store.record_array_task("42","42_1")
        with self.assertRaises(ValueError):self.store.record_array_task("42","43_1")

    def test_unicode_export_receipt_is_bound_to_the_current_checkpoint_and_invalidates_cache(self):
        self.job()
        latest = {"generation":7,"step":12,"world_size":2,"run_id":"run-é","binding_sha256":"a"*64,
                  "manifest_sha256":"b"*64,"integrity_verified":True,"directory":"/scratch/sauvegarde-é"}
        runtime = {"schema":"romeo-runtime-observation-v1","job_id":"42","run_id":"run-é","world_size":2,
                   "binding_sha256":"a"*64,"latest_checkpoint":latest,"observed_at":time.time()}
        self.store.save_observation("checkpoint:42",TARGET,runtime)
        identifier = "a"*32
        directory = self.root/"transfers"/identifier
        directory.mkdir(parents=True)
        plan = {"id":identifier,"direction":"download","local_path":"sauvegarde-é","remote_path":"/scratch/sauvegarde-é",
                "recursive":True,"verify":False,"target":TARGET,"created_at":time.time()}
        plan["sha256"] = hashlib.sha256(json.dumps(plan,sort_keys=True).encode()).hexdigest()
        (directory/"plan.json").write_text(json.dumps(plan),encoding="utf-8")
        (directory/"status.json").write_text(json.dumps({"ok":True,"transfer_id":identifier,"state":"completed_unverified"}),encoding="utf-8")
        export = {"job_id":"42","transfer_id":identifier,"checkpoint":latest,"transfer_sha256":plan["sha256"],"local_path":"sauvegarde-é"}
        export["sha256"] = digest(export)
        exports = self.root/"checkpoint-exports"
        exports.mkdir()
        (exports/(identifier+".json")).write_text(json.dumps(export,ensure_ascii=False),encoding="utf-8")
        catalog = self.catalog()
        first = catalog.snapshot()["workspace"]
        self.assertIsNone(first["recovery"]["independent_backup"])
        self.assertIsNone(first["recovery"]["resume_observed"])
        self.assertEqual(first["links"][0]["basis"],"export de checkpoint signé")
        receipt = {"export_sha256":export["sha256"],"manifest_sha256":"b"*64,"independent_backup":True,
                   "checkpoint_integrity_verified":True,"verified_at":time.time()}
        proof_path = exports/(identifier+".verified.json")
        proof_path.write_text(json.dumps(receipt),encoding="utf-8")
        self.assertIsNone(catalog.snapshot({"collect":False})["workspace"]["recovery"]["independent_backup"])
        self.assertTrue(catalog.snapshot()["workspace"]["recovery"]["independent_backup"])
        proof_path.write_text(json.dumps({**receipt,"manifest_sha256":"c"*64}),encoding="utf-8")
        self.assertIsNone(catalog.snapshot()["workspace"]["recovery"]["independent_backup"])
        proof_path.write_text(json.dumps(receipt),encoding="utf-8")
        self.store.save_observation("checkpoint:42",TARGET,{**runtime,"latest_checkpoint":{**latest,"manifest_sha256":"d"*64}})
        self.assertIsNone(catalog.snapshot()["workspace"]["recovery"]["independent_backup"])

    def test_checkpoint_notification_does_not_require_a_slurm_observation(self):
        self.store.record("42","synthetic","cpu","x64cpu","/synthetic","out","err","")
        catalog = self.catalog()
        catalog.snapshot()
        latest = {"generation":7,"step":12,"world_size":2,"run_id":"run","binding_sha256":"a"*64,"manifest_sha256":"b"*64,"integrity_verified":True}
        self.store.save_observation("checkpoint:42",TARGET,{"schema":"romeo-runtime-observation-v1","job_id":"42","run_id":"run",
            "world_size":2,"binding_sha256":"a"*64,"latest_checkpoint":latest,"observed_at":time.time()})
        result = catalog.snapshot()
        self.assertEqual(result["notifications"][0]["message"],"Checkpoint vérifié · génération 7")
        self.assertEqual(len(catalog.snapshot()["notifications"]),1)

    def test_allocations_use_saved_slurm_state_and_known_remaining_time(self):
        self.job()
        saved = self.store.prepare_submission({"kind":"allocation","target":TARGET,"preview":{}})
        self.store.update_submission(saved["plan_id"],"submitted",{"job_id":"42"})
        result = self.catalog().snapshot()["sessions"][0]
        self.assertTrue(result["ready"])
        self.assertIsNone(result["expires_at"])
        self.store.save_observation("42",TARGET,{"ok":True,"job_id":"42","state":"RUNNING","remaining":"00:30:00"})
        result = self.catalog().snapshot()["sessions"][0]
        self.assertAlmostEqual(result["expires_at"]-result["observed_at"],1800)

    def test_legacy_service_trace_requires_both_service_and_job_identity(self):
        self.job()
        saved = self.store.prepare_submission({"kind":"service","target":TARGET,"preview":{"service":{"type":"jupyter"}}})
        self.store.update_submission(saved["plan_id"],"submitted",{"job_id":"42"})
        catalog = self.catalog()
        self.assertIsNone(catalog.snapshot()["sessions"][0]["observed_at"])
        self.store.save_observation("42",TARGET,{"ok":True,"job_id":"42","service_id":saved["plan_id"],"state":"ready"})
        result = catalog.snapshot()["sessions"][0]
        self.assertIsNotNone(result["observed_at"])
        self.assertIsNone(result["ready"])

    def test_requested_time_uses_explicit_full_slurm_duration_only(self):
        from romeo_mcp.terminal_hpc import resources
        self.assertEqual(resources("#SBATCH --time=01:30:00",{})["requested"]["time_limit_seconds"],5400)
        self.assertNotIn("time_limit_seconds",resources("#SBATCH --time=01:30",{})["requested"])

    def test_remaining_dependencies_require_the_saved_scheduler_observation(self):
        self.job("42","#SBATCH --dependency=afterok:43",state="PENDING")
        catalog=self.catalog()
        self.assertIsNone(catalog.snapshot()["workspace"]["group"]["remaining_dependencies"])
        self.store.save_observation("42",TARGET,{"ok":True,"job_id":"42","state":"PENDING","dependencies_remaining":"afterok:43(unfulfilled)"})
        self.assertEqual(catalog.snapshot()["workspace"]["group"]["remaining_dependencies"],"afterok:43(unfulfilled)")
        self.store.save_observation("42",TARGET,{"ok":True,"job_id":"42","state":"RUNNING","dependencies_remaining":""})
        self.assertEqual(catalog.snapshot()["workspace"]["group"]["remaining_dependencies"],"")

    def test_services_are_separate_from_slurm_and_credentials_never_cross_contract(self):
        self.job()
        saved=self.store.prepare_submission({"kind":"service","target":TARGET,"preview":{"service":{"type":"jupyter","credential_path":"/secret/token","port":8888}}})
        self.store.update_submission(saved["plan_id"],"submitted",{"job_id":"42"})
        self.store.save_observation("service:"+saved["plan_id"],TARGET,{"ok":True,"job_id":"42","service_id":saved["plan_id"],"state":"ready","current_state_observed":True})
        result=self.catalog().snapshot()
        self.assertEqual(result["jobs"][0]["state"],"RUNNING");self.assertTrue(result["sessions"][0]["ready"])
        self.assertIsNone(result["sessions"][0]["expires_at"])
        self.assertNotIn("/secret/token",json.dumps(result));self.assertNotIn("synthetic.example",json.dumps(result))

    def test_sharing_projection_masks_names_logs_and_paths_without_mutating_source(self):
        self.job();self.store.save_observation("logs:42",TARGET,{"ok":True,"job_id":"42","content":"private-log-path","stream":"out"})
        original=self.catalog().snapshot();masked=project(original)
        encoded=json.dumps(masked);self.assertNotIn("private-project-name",encoded);self.assertNotIn("private-log-path",encoded)
        self.assertEqual(masked["jobs"][0]["id"],"42");self.assertEqual(original["jobs"][0]["name"],"private-project-name")

    def test_remote_is_explicit_allowlisted_and_demo_never_imports_ssh(self):
        with patch("romeo_mcp.ssh.session",side_effect=AssertionError("no SSH")):
            self.assertTrue(perform("status","42",demo=True)["ok"])
        with self.assertRaises(ValueError):perform("submit","42",demo=True)
        with self.assertRaises(ValueError):perform("status","42; command",demo=True)


if __name__=="__main__":unittest.main(verbosity=2)
