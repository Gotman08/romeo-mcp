"""Fichiers, preuves, quotas et vrais processus : aucune connexion au cluster."""
import asyncio
import copy
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import offline
from commun import RACINE
from romeo_mcp import checkpoint_protocol as cp, checkpoint_storage as storage, checkpoint_operations as operations
from romeo_mcp import checkpoint_runner as runner, checkpoint_jobs, parallel_runtime as parallel
from romeo_mcp import plans, reproducibility, execution_backend, server, transfers, workload_preparation
from romeo_mcp.cluster import ClusterError
from romeo_mcp.registry import Registry
from romeo_mcp.slurm import JobSpec, plan_job
from romeo_mcp.ssh import Result, SSHError


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="romeo-checkpoint-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.code = self.root / "programme.py"
        self.data = self.root / "donnees.bin"
        self.code.write_text("programme original", encoding="utf-8")
        self.data.write_bytes(b"input")
        self.binding = cp.workload_binding("programme", [str(self.code)], [str(self.data)], {"architecture": "x64cpu"})
        self.run = "calcul-A"
        self.backup = self.root / "backup"

    def checkpoint(self, generation=1, step=10, world=2):
        directory = cp.generation_directory(self.root, self.run, generation)
        directory.mkdir(parents=True)
        files = []
        for rank in range(world):
            name = "rank-%d.bin" % rank
            (directory / name).write_bytes(("step=%d rank=%d" % (step, rank)).encode())
            files.append({"path": name, "ranks": [rank]})
        path = cp.publish(self.root, self.run, generation, step, world, files, [step] * world, self.binding)
        return cp.verify_checkpoint(path, binding=self.binding, world_size=world)

    def test_latest_complete_is_not_latest_modified_or_partial(self):
        first = self.checkpoint(1)
        bad = self.checkpoint(2, step=20)
        Path(bad["directory"], "rank-1.bin").write_bytes(b"corrupt")
        cp.generation_directory(self.root, self.run, 3).mkdir()
        selection = cp.discover(self.root, self.run, binding=self.binding, world_size=2)
        self.assertEqual(selection["checkpoint"]["manifest_sha256"], first["manifest_sha256"])
        self.assertEqual([r["generation"] for r in selection["rejected"]], [3, 2])
        metadata = cp.discover(self.root, self.run, verify_files=False)
        self.assertEqual(metadata["checkpoint"]["manifest"]["generation"], 2)
        self.assertFalse(metadata["checkpoint"]["integrity_verified"])

    def test_changed_program_data_environment_or_world_rejects_resume(self):
        self.checkpoint()
        self.data.write_bytes(b"other input")
        changed = cp.workload_binding("programme", [str(self.code)], [str(self.data)], {"architecture": "x64cpu"})
        for binding, world in ((changed, 2), ({**self.binding, "environment": {"architecture": "armgpu"}}, 2),
                               (self.binding, 4)):
            self.assertIsNone(cp.discover(self.root, self.run, binding=binding, world_size=world)["checkpoint"])
        self.assertIsNone(cp.discover(self.root, self.run, expected_binding_sha256="0" * 64)["checkpoint"])

    def test_manifest_is_immutable_and_requires_all_ranks_at_same_step(self):
        checkpoint = self.checkpoint()
        manifest = checkpoint["manifest"]
        for update in ({"rank_steps": [10, 9]}, {"complete": False},
                       {"files": [{**manifest["files"][0], "ranks": [0]}]}, {"generation": True}):
            with self.assertRaises(ValueError):
                cp.validate_manifest({**manifest, **update}, checkpoint["directory"])
        with self.assertRaises(FileExistsError):
            cp.atomic_json(checkpoint["manifest_path"], manifest, immutable=True)
        self.assertEqual(cp.read_json(checkpoint["manifest_path"]), manifest)

    def test_traversal_symlinks_and_budgets_are_rejected(self):
        checkpoint = self.checkpoint()
        for name in ("../donnees.bin", "/etc/passwd", "sub/../../file", "sub\\file"):
            with self.assertRaises(ValueError):
                cp.safe_file(checkpoint["directory"], name)
        with self.assertRaises(ValueError):
            cp.verify_checkpoint(checkpoint["manifest_path"], max_bytes=1)
        with self.assertRaises(ValueError):
            cp.hash_file(self.data, deadline=time.monotonic() - 1)
        duplicate = self.root / "duplicate.json"
        duplicate.write_text('{"complete":true,"complete":false}', encoding="utf-8")
        with self.assertRaises(ValueError):
            cp.read_json(duplicate)
        try:
            symlink = self.root / "linked"
            symlink.symlink_to(self.data)
        except OSError:
            return
        with self.assertRaises(ValueError):
            cp.hash_file(symlink)

    def context(self):
        attempt = self.root / "attempt"
        context = {"attempt_id": "attempt-A", "run_id": self.run, "job_id": "123", "world_size": 2,
                   "binding_sha256": cp.digest(self.binding), "checkpoint_sha256": "a" * 64, "checkpoint_step": 10}
        cp.atomic_json(attempt / "context.json", context)
        return attempt, context

    def test_loaded_receipts_alone_and_spoofed_attempt_are_not_a_resume(self):
        attempt, context = self.context()
        with patch.dict(os.environ, {"ROMEO_CHECKPOINT_ATTEMPT": str(attempt)}):
            for rank in (0, 1):
                cp.record_event("loaded", 10, rank=rank)
            self.assertFalse(cp.observe_receipts(attempt, context)["resume_validated"])
            cp.record_event("progress", 11, rank=0)
            self.assertFalse(cp.observe_receipts(attempt, context)["resume_validated"])
            bad = cp.record_event("progress", 11, rank=1)
            cp.atomic_json(attempt / "receipts" / "progress-1.json", {**bad, "attempt_id": "other"})
            self.assertFalse(cp.observe_receipts(attempt, context)["resume_validated"])
            cp.record_event("progress", 11, rank=1)
            self.assertTrue(cp.observe_receipts(attempt, context)["resume_validated"])
            cp.record_event("completed", 9, rank=0)
            cp.record_event("completed", 9, rank=1)
            self.assertFalse(cp.observe_receipts(attempt, context)["application_completion_observed"])

    def test_signal_ack_requires_every_rank_and_correlated_checkpoint(self):
        attempt, context = self.context()
        checkpoint = self.checkpoint()
        request = {"request_id": "request-A"}
        cp.atomic_json(attempt / "signal.json", request)
        checkpoint["manifest"]["signal_request_id"] = request["request_id"]
        with patch.dict(os.environ, {"ROMEO_CHECKPOINT_ATTEMPT": str(attempt)}):
            cp.record_event("signal_ack", 10, rank=0)
            evidence = cp.observe_receipts(attempt, context)
            self.assertFalse(runner.signal_evidence(evidence, checkpoint, request, 2)["checkpoint_after_signal_verified"])
            cp.record_event("signal_ack", 10, rank=1)
            evidence = cp.observe_receipts(attempt, context)
            self.assertTrue(runner.signal_evidence(evidence, checkpoint, request, 2)["checkpoint_after_signal_verified"])
            checkpoint["manifest"]["signal_request_id"] = "old"
            self.assertFalse(runner.signal_evidence(evidence, checkpoint, request, 2)["checkpoint_after_signal_verified"])

    def test_quota_checks_blocks_inodes_in_doubt_grace_and_unknown(self):
        healthy = "gpfs scratch USR 100 1000 2000 10 none 10 100 200 2 none"
        self.assertEqual(storage.quota_capacity(healthy, "gpfs", "scratch", 1024, 1)["files"], 10)
        for output, required_bytes, required_files in ((healthy, 1024 * 900, 1), (healthy, 1, 90),
                                                       (healthy.replace("none", "expired"), 1, 1), ("unknown", 1, 1)):
            with self.assertRaises(ValueError):
                storage.quota_capacity(output, "gpfs", "scratch", required_bytes, required_files)

    def test_failed_copy_keeps_original_and_never_publishes_destination(self):
        checkpoint = self.checkpoint()
        with patch.object(storage, "_copy_file", side_effect=OSError("disque plein")):
            with self.assertRaises(OSError):
                storage.copy_verified(checkpoint, self.backup, {}, quota_checker=lambda *_: {})
        self.assertTrue(Path(checkpoint["manifest_path"]).is_file())
        self.assertFalse((self.backup / self.run / Path(checkpoint["directory"]).name).exists())
        copied = storage.copy_verified(checkpoint, self.backup, {}, quota_checker=lambda *_: {"checked": True})
        self.assertTrue(copied["copy_validated"])
        self.assertFalse(copied["independent_backup"])
        self.assertEqual(cp.verify_checkpoint(Path(copied["directory"]) / "manifest.json")["manifest_sha256"], checkpoint["manifest_sha256"])

    def test_copy_quota_counts_all_shared_ancestors_before_creating_directories(self):
        directory = cp.generation_directory(self.root, self.run, 1)
        files = [{"path": "state/shared/deep/rank-%d.bin" % rank, "ranks": [rank]} for rank in range(2)]
        for entry in files:
            target = directory / entry["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"saved state")
        manifest = cp.publish(self.root, self.run, 1, 10, 2, files, [10, 10], self.binding)
        checkpoint = cp.verify_checkpoint(manifest, binding=self.binding, world_size=2)
        backup = self.root / "new" / "nested" / "backup"

        def limited_quota(_policy, required_bytes, required_files):
            # Two files, three shared ancestors, four destination ancestors,
            # and four inodes reserved for the generation and metadata.
            self.assertEqual(required_files, 13)
            return storage.quota_capacity("gpfs scratch USR 0 0 0 0 none 0 12 12 0 none",
                                          "gpfs", "scratch", required_bytes, required_files)

        with self.assertRaisesRegex(ValueError, "inodes"):
            storage.copy_verified(checkpoint, backup, {}, quota_checker=limited_quota)
        self.assertFalse(backup.exists())
        self.assertTrue(Path(checkpoint["manifest_path"]).is_file())

    def test_retention_preserves_unprotected_generations_and_latest(self):
        checkpoints = [self.checkpoint(i, step=i) for i in range(4)]
        storage.copy_verified(checkpoints[0], self.backup, {}, quota_checker=lambda *_: {})
        result = storage.retain_protected(self.root, self.backup, checkpoints[3], 2)
        self.assertEqual(result["removed"], [Path(checkpoints[0]["directory"]).name])
        self.assertTrue(Path(checkpoints[1]["directory"]).exists())
        self.assertTrue(Path(checkpoints[3]["directory"]).exists())
        self.assertTrue((self.backup / self.run / Path(checkpoints[0]["directory"]).name).exists())

    def test_incomplete_generations_do_not_replace_valid_retention_slots(self):
        checkpoints = [self.checkpoint(i, step=i) for i in range(4)]
        for item in checkpoints:
            storage.copy_verified(item, self.backup, {}, quota_checker=lambda *_: {})
        cp.generation_directory(self.root, self.run, 5).mkdir()
        cp.generation_directory(self.root, self.run, 6).mkdir()
        result = storage.retain_protected(self.root, self.backup, checkpoints[3], 2)
        self.assertTrue(Path(checkpoints[2]["directory"]).exists())
        self.assertTrue(Path(checkpoints[3]["directory"]).exists())
        self.assertEqual(len(result["kept_valid_generations"]), 2)

    def test_checkpoint_export_verifies_local_copy_and_dates_cached_evidence(self):
        checkpoint = self.checkpoint()
        expected = {**runner.checkpoint_summary(checkpoint), "directory": "/scratch_p/student/ckpts/calcul-A/generation-00000000000000000001"}
        store = Registry(self.root / "registry.db")
        self.addCleanup(store.close)
        connection = SimpleNamespace(host="invalid-offline-host", user="student", home="/home/test", scratch="/scratch_p/student", path_aliases=[])
        with patch.object(operations, "registry", return_value=store), patch.object(transfers, "registry", return_value=store), \
             patch.object(transfers, "session", return_value=connection), patch.object(operations, "runtime_status", return_value={
                 "ok": True, "runtime": {"latest_checkpoint": expected}}):
            prepared = operations.export_prepare("123", str(self.root / "export"))
            self.assertFalse(prepared["independent_backup"])
            transfer_id = prepared["transfer_id"]
            destination = Path(prepared["plan"]["local_path"])
            shutil.copytree(checkpoint["directory"], destination)
            completed = {"ok": True, "transfer_id": transfer_id, "state": "completed_unverified", "result_validated": False}
            with patch.object(transfers, "status", return_value=completed):
                verified = operations.export_status(transfer_id)
                self.assertTrue(verified["independent_backup"], verified)
                self.assertTrue(verified["current_integrity_observed"])
                (destination / "rank-0.bin").write_bytes(b"damaged")
                historical = operations.export_status(transfer_id)
                self.assertFalse(historical["current_integrity_observed"])
                self.assertIn("verification_age_seconds", historical)
                refreshed = operations.export_status(transfer_id, refresh=True)
                self.assertFalse(refreshed["checkpoint_integrity_verified"])
                self.assertFalse(refreshed["independent_backup"])

    def test_language_neutral_cli_emits_correlated_receipts(self):
        attempt, context = self.context()
        environment = {**os.environ, "ROMEO_CHECKPOINT_ATTEMPT": str(attempt)}
        result = subprocess.run([sys.executable, str(Path(cp.__file__)), "event", "loaded", "10", "--rank", "1"],
                                env=environment, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout)
        self.assertEqual(receipt["checkpoint_sha256"], context["checkpoint_sha256"])
        self.assertEqual(receipt["rank"], 1)


class ParallelTests(unittest.TestCase):
    def test_gpu_per_task_reservation_and_openmp_resources(self):
        spec = JobSpec("mpi-gpu", "./code", nodes=2, ntasks_per_node=2, cpus_per_task=8,
                       gpus_per_task=1, gpu_bind="single:1", distributed="mpi", reservation="cours-42")
        plan = plan_job(spec, "/scratch_p/student")
        self.assertEqual(plan.total_gpus, 4)
        self.assertIn("#SBATCH --gpus-per-task=1", plan.script)
        self.assertIn("#SBATCH --gpus-per-node=2", plan.script)
        self.assertIn("#SBATCH --reservation=cours-42", plan.script)
        self.assertIn("#SBATCH --gpu-bind=single:1", plan.script)
        omp = plan_job(JobSpec("omp", "./omp", distributed="openmp", cpus_per_task=24, omp_proc_bind="spread"), "/scratch_p/student")
        self.assertIn("export OMP_PROC_BIND=spread", omp.script)
        self.assertIn("export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-1}", omp.script)
        self.assertIn("srun --cpu-bind=cores ./omp", omp.script)
        for kwargs in ({"gpus_per_task": 1, "gpus_per_node": 2}, {"reservation": "bad\n#SBATCH"},
                       {"cpu_bind": "cores; echo injected"}, {"gpu_bind": "single:1"},
                       {"distributed": "openmp", "nodes": 2}):
            with self.assertRaises(ClusterError):
                plan_job(JobSpec("bad", "./code", **kwargs), "/scratch_p/student")

    def test_spack_old_and_new_compilers_variants_hashes(self):
        values = [{"name": "openmpi", "version": "5.0.5", "hash": "a" * 32, "arch": {"target": "zen4"},
                   "parameters": {"cuda": False, "fabrics": ["ucx"]},
                   "dependencies": [{"name": "gcc", "hash": "b" * 32, "parameters": {"virtuals": ["c", "cxx"]}}]},
                  {"name": "gcc", "version": "11.4.1", "hash": "b" * 32, "parameters": {}, "arch": {}}]
        parsed = parallel.parse_spack_catalog("Spack environment ready\n" + json.dumps(values))
        mpi = next(p for p in parsed if p["name"] == "openmpi")
        self.assertEqual(mpi["load_spec"], "/" + "a" * 32)
        self.assertEqual(mpi["compilers"][0]["version"], "11.4.1")
        self.assertEqual(mpi["variants"]["fabrics"], ["ucx"])
        self.assertFalse(parallel.parse_spack_catalog("openmpi@4.1.7")[0]["details_available"])
        self.assertRaises(ValueError, parallel.parse_spack_catalog, "[{ incomplete")

    def test_mpi_request_rejects_wrong_provider_arch_and_bad_hash(self):
        self.assertEqual(parallel.validate_mpi_request({"executable": "/scratch/code"}, "armgpu", "mpi")["provider"], "hpcx")
        for request, arch, family in (({"provider": "openmpi", "executable": "/code"}, "armgpu", "mpi"),
                                      ({"executable": "/code", "spack_hash": "../foo"}, "x64cpu", "mpi"),
                                      ({"executable": "/code"}, "x64cpu", "openmp")):
            self.assertRaises(ValueError, parallel.validate_mpi_request, request, arch, family)

    def test_elf_architecture_is_read_without_executing_the_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "binary"
            header = bytearray(20)
            header[:6] = b"\x7fELF\x02\x01"
            header[18:20] = (183).to_bytes(2, "little")
            path.write_bytes(header)
            self.assertEqual(parallel.elf_machine(path), "aarch64")
            path.write_bytes(b"not an elf")
            self.assertRaises(ValueError, parallel.elf_machine, path)

    @unittest.skipIf(os.name == "nt", "Chemins ELF/ldd POSIX")
    def test_mpi_linkage_checks_selected_library_hash_and_spack(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mpi = root / "openmpi"
            (mpi / "bin").mkdir(parents=True)
            (mpi / "lib").mkdir()
            compiler = mpi / "bin" / "mpicc"
            compiler.touch()
            header = bytearray(20)
            header[:6] = b"\x7fELF\x02\x01"
            header[18:20] = (62).to_bytes(2, "little")
            executable, library = root / "code", mpi / "lib" / "libmpi.so"
            executable.write_bytes(header)
            library.write_bytes(header)
            responses = {"--showme:command": "gcc", "--showme:version": "Open MPI 5.0.5",
                         "--showme:link": "-L%s -lmpi" % (mpi / "lib"), "--version": "gcc 11.4.1"}
            def output(argv):
                return "libmpi.so => %s (0xabc)" % library if argv[0] == "ldd" else responses[argv[1]]
            request = {"provider": "openmpi", "executable": str(executable), "spack_hash": "abcdefg", "compiler": "gcc@11.4.1",
                       "library_sha256": cp.hash_file(library)["sha256"]}
            with patch.object(parallel.platform, "machine", return_value="x86_64"), patch.object(parallel.shutil, "which", return_value=str(compiler)), \
                 patch.object(parallel, "command_output", side_effect=output), patch.dict(os.environ, {"SPACK_LOADED_HASHES": "abcdefg123456789"}):
                observed = parallel.verify_mpi(request, "x64cpu")
                self.assertTrue(observed["linkage_verified"])
                self.assertFalse(observed["mpi_collectives_validated"])
                self.assertRaises(ValueError, parallel.verify_mpi, {**request, "library_sha256": "0" * 64}, "x64cpu")
                self.assertRaises(ValueError, parallel.verify_mpi, {**request, "spack_hash": "missing"}, "x64cpu")

    def test_mcp_catalog_advertises_typed_parallel_and_resume_actions(self):
        tools = {t.name: t for t in asyncio.run(server.server.list_tools())}
        for name in ("job_prepare", "job_resilient_prepare"):
            self.assertTrue({"nodes", "ntasks_per_node", "distributed", "cpu_bind", "reservation", "gpus_per_task", "mpi_environment"}.issubset(tools[name].input_schema["properties"]))
        for name in ("job_resume", "checkpoint_protect"):
            self.assertEqual(set(tools[name + "_submit"].input_schema["properties"]), {"plan_id", "confirm"})
            self.assertFalse(tools[name + "_submit"].annotations.read_only_hint)
        self.assertTrue(tools["job_resume_status"].annotations.read_only_hint)
        self.assertFalse(tools["checkpoint_export_status"].annotations.read_only_hint)


class OperationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="romeo-checkpoint-registry-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.store = Registry(self.root / "registry.db")
        self.addCleanup(self.store.close)
        self.session = SimpleNamespace(host="invalid-offline-host", user="student", home="/home/test",
                                       scratch="/scratch_p/student", path_aliases=[], write_file=lambda *_a, **_k: None)
        self.observation = {"schema": "romeo-runtime-observation-v1", "job_id": "123", "run_id": "run-A", "world_size": 4,
                            "state": "stopped", "binding_sha256": "b" * 64, "resume_validated": False, "observed_at": time.time()}
        spec = JobSpec("test", "./code", nodes=2, ntasks_per_node=2, cpus_per_task=4, distributed="mpi", arch="x64cpu",
                       checkpoint_dir="/scratch_p/student/ckpts", workdir="/scratch_p/student/code", signal_before=300,
                       checkpoint_contract={"run_id": "run-A", "code_files": ["/scratch_p/student/code/app"], "data_files": []})
        self.plan = plan_job(spec, self.session.scratch)
        self.store.record(job_id="123", name="test", partition=self.plan.partition, arch=self.plan.arch, workdir=self.plan.workdir,
                          stdout_glob="log.out", stderr_glob="log.err", script=self.plan.script,
                          provenance={"checkpoint_job": {"spec": __import__("dataclasses").asdict(spec), "architecture": self.plan.arch,
                                      "target": {"host": self.session.host, "user": self.session.user, "account": spec.account}}})
        for module in (operations, plans, execution_backend, transfers):
            self.enterContext(patch.object(module, "registry", return_value=self.store))
            self.enterContext(patch.object(module, "session", return_value=self.session))
        self.enterContext(patch.object(operations, "_contexte_chemins", return_value=(self.session.home, self.session.scratch, [], None)))
        self.enterContext(patch.object(plans, "_contexte_chemins", return_value=(self.session.home, self.session.scratch, [], None)))
        self.enterContext(patch.object(operations, "_sh", side_effect=self.remote))

    def remote(self, _connection, command, **_kwargs):
        if command.startswith("head "):
            return Result(0, json.dumps(self.observation), 0)
        return Result(0, "###LIVE\n###PAST\n123|test|instant|FAILED|01:00|1:0|2026-01-01|2026-01-01", 0)

    def test_resume_plan_keeps_topology_and_pins_source_binding_without_submission(self):
        result = operations.prepare_from_job("123")
        self.assertTrue(result["ok"], result)
        self.assertFalse(result["submitted"])
        saved = self.store.prepared_submission(result["plan_id"])["payload"]
        spec = saved["entries"][0]["plan"]["spec"]
        self.assertEqual((spec["nodes"], spec["ntasks_per_node"], spec["distributed"]), (2, 2, "mpi"))
        self.assertTrue(spec["checkpoint_contract"]["require_resume"])
        self.assertEqual(spec["checkpoint_contract"]["expected_binding_sha256"], "b" * 64)
        self.assertEqual(len(saved["runtime_files"]), 5)
        self.assertNotEqual(spec["runtime_id"], self.plan.spec.runtime_id)

    def test_failed_ssh_keeps_dated_observation_without_claiming_current_resume(self):
        first = operations.runtime_status("123")
        self.assertTrue(first["runtime_observed"])
        with patch.object(operations, "_sh", side_effect=SSHError("disconnected")):
            stale = operations.runtime_status("123")
        self.assertFalse(stale["runtime_observed"])
        self.assertFalse(stale["resume_validated"])
        self.assertEqual(stale["last_observation"]["result"], first["runtime"])
        self.session.host = "another-host"
        self.assertRaises(ValueError, operations.runtime_status, "123")

    def test_active_source_job_cannot_be_resumed(self):
        with patch.object(operations, "observe_source_job", side_effect=ValueError("active")):
            self.assertRaises(ValueError, operations.prepare_from_job, "123")

    def test_checkpoint_request_is_not_a_saved_checkpoint(self):
        self.observation["state"] = "running"
        commands = []
        def remote(_session, command, **_kwargs):
            commands.append(command)
            if command.startswith("head "):
                return Result(0, json.dumps(self.observation), 0)
            if command.startswith("scancel "):
                return Result(0, "", 0)
            return Result(0, "###LIVE\n123|test|instant|RUNNING|01:00|01:00|2|nodes\n###START", 0)
        with patch.object(operations, "_sh", side_effect=remote):
            accepted = operations.request_checkpoint("123")
            self.assertTrue(accepted["signal_requested"])
            self.assertFalse(accepted["checkpoint_verified"])
            self.assertFalse(accepted["application_acknowledged"])
            self.assertIn("scancel --batch --signal=USR1 123", commands)
            self.observation["signal_requested"] = True
            self.observation["checkpoint_after_signal_verified"] = False
            commands.clear()
            self.assertTrue(operations.request_checkpoint("123")["already_requested"])
            self.assertFalse(any(c.startswith("scancel ") for c in commands))

    def test_helpers_are_sealed_once_for_all_resilient_segments(self):
        with patch.object(workload_preparation, "session", return_value=self.session), patch.object(workload_preparation, "_contexte_chemins",
                return_value=(self.session.home, self.session.scratch, [], None)):
            prepared = workload_preparation.job_resilient_prepare("test", "./app", gpus_per_node=0, max_total_time="3h",
                checkpoint_contract={"code_files": ["/scratch_p/student/code/app"]})
        self.assertTrue(prepared["ok"], prepared)
        payload = self.store.prepared_submission(prepared["plan_id"])["payload"]
        self.assertEqual(len(payload["entries"]), 3)
        self.assertEqual(len(payload["runtime_files"]), 5)
        self.assertEqual({e["plan"]["spec"]["runtime_id"] for e in payload["entries"]}, {payload["entries"][0]["plan"]["spec"]["runtime_id"]})
        writes = []
        self.session.write_file = lambda path, content, mode=None: writes.append((path, content))
        with patch.object(execution_backend, "_sh", return_value=Result(0, "456", 0)), patch.object(reproducibility, "observe_files",
                return_value={"git": {"status": "unavailable"}}):
            submitted = plans.submit_prepared("resilient", prepared["plan_id"], True)
        self.assertTrue(submitted["ok"], submitted)
        self.assertEqual(len([p for p, _ in writes if ".romeo-runtime/" in p]), 5)


# Fixture de processus : deux rangs comme srun, sans simuler une communication
# MPI reelle. Chaque rang applique le contrat apres une barriere applicative.
FAKE_SRUN = '''#!/usr/bin/env python3
import os,signal,subprocess,sys,time
args=sys.argv[1:]
while args and args[0].startswith("--"): args.pop(0)
children=[]
reader,writer=os.pipe();os.set_inheritable(writer,True)
def forward(s,f):
 for p in children:
  if p.poll() is None: os.killpg(p.pid,s)
signal.signal(signal.SIGUSR1,forward); signal.signal(signal.SIGTERM,forward)
for rank in range(int(os.environ["SLURM_NTASKS"])):
 children.append(subprocess.Popen(args,env={**os.environ,"SLURM_PROCID":str(rank),"PMI_FD":str(writer)},
                                  start_new_session=True,pass_fds=(writer,)))
os.close(writer)
while any(p.poll() is None for p in children): time.sleep(.05)
assert len(os.read(reader,1024))==len(children),"Descripteurs PMI perdus"
sys.exit(max(p.returncode for p in children))
'''
APPLICATION = '''import os,signal,time
from pathlib import Path
import checkpoint_protocol as cp
context=cp.application_context(); rank=int(os.environ["SLURM_PROCID"]); world=context["world_size"]
os.write(int(os.environ["PMI_FD"]),b"1")
attempt=Path(os.environ["ROMEO_CHECKPOINT_ATTEMPT"]); root=Path(os.environ["ROMEO_CHECKPOINT_DIR"])
mode=os.environ.get("EXAMPLE_MODE","save"); step=0
if context["checkpoint_path"]:
 manifest=cp.read_json(context["checkpoint_path"])
 state=cp.read_json(Path(context["checkpoint_path"]).parent/('rank-%d.json'%rank)); step=state["step"]
 if mode!="missing" or rank==0:
  cp.record_event("loaded",step); step+=1; cp.record_event("progress",step)
 if mode in ("complete","missing"):
  cp.record_event("completed",step); raise SystemExit(0)
requested=False
def signal_request(s,f):
 global requested
 requested=True
signal.signal(signal.SIGUSR1,signal_request)
(attempt/('ready-%d'%rank)).touch()
while not requested: time.sleep(.05)
step=5; directory=cp.generation_directory(root,context["run_id"],1); directory.mkdir(parents=True,exist_ok=True)
cp.atomic_json(directory/('rank-%d.json'%rank),{"step":step},immutable=True)
cp.record_event("signal_ack",step)
if rank==0:
 while not all((attempt/'receipts'/('signal_ack-%d.json'%r)).exists() for r in range(world)): time.sleep(.05)
 cp.publish(root,context["run_id"],1,step,world,[{"path":'rank-%d.json'%r,"ranks":[r]} for r in range(world)],
            [step]*world,context["binding"],signal_request_id=cp.read_json(attempt/'signal.json')["request_id"])
else:
 while not (directory/'manifest.json').exists(): time.sleep(.05)
raise SystemExit(3)
'''


@unittest.skipIf(os.name == "nt", "Signaux POSIX et srun testes sur Linux/macOS ; contrats purs testes aussi sur Windows")
class ProcessTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="romeo-checkpoint-process-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.app = self.root / "application.py"
        self.app.write_text(APPLICATION, encoding="utf-8")
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        (bin_dir / "srun").write_text(FAKE_SRUN, encoding="utf-8")
        (bin_dir / "srun").chmod(0o700)
        spec = JobSpec("example", shlex.quote(sys.executable) + " " + shlex.quote(str(self.app)), nodes=2,
                       ntasks_per_node=1, distributed="mpi", cpus_per_task=1, workdir=str(self.root), arch="x64cpu",
                       checkpoint_dir=str(self.root / "checkpoints"), checkpoint_contract={"run_id": "example-run",
                       "code_files": [str(self.app)], "runtime_python": sys.executable, "resume_timeout_seconds": 2})
        plan = plan_job(spec, str(self.root))
        for artifact in checkpoint_jobs.runtime_files(plan):
            path = Path(artifact["path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(artifact["content"], encoding="utf-8")
        self.runtime = Path(checkpoint_jobs.runtime_directory(spec, plan.workdir))
        self.env = {**os.environ, "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"], "SLURM_NTASKS": "2",
                    "SPACK_LOADED_HASHES": "", "RANK": "0"}
        self.env.pop("RANK", None)
        self.log = (self.root / "log.txt").open("w+")
        self.addCleanup(self.log.close)

    def start(self, jid, mode):
        child = subprocess.Popen([sys.executable, str(self.runtime / "checkpoint_runner.py"), str(self.runtime / "config.json")],
                                 stdout=self.log, stderr=self.log, env={**self.env, "SLURM_JOB_ID": jid, "EXAMPLE_MODE": mode})
        self.addCleanup(lambda: child.kill() if child.poll() is None else None)
        return child

    def status(self, jid):
        return cp.read_json(self.root / "checkpoints" / "example-run" / "jobs" / (jid + ".json"))

    def save_first(self):
        child = self.start("100", "save")
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                status = self.status("100")
                attempt = self.root / "checkpoints" / "example-run" / "attempts" / status["attempt_id"]
                if all((attempt / ("ready-%d" % rank)).exists() for rank in range(2)):
                    break
            except (OSError, ValueError):
                pass
            time.sleep(0.05)
        else:
            self.log.flush()
            self.fail("Application non demarree : " + (self.root / "log.txt").read_text())
        child.send_signal(signal.SIGUSR1)
        self.assertEqual(child.wait(timeout=15), 3)
        return self.status("100")

    def test_signal_all_ranks_checkpoint_then_real_load_progress_and_skip(self):
        saved = self.save_first()
        self.assertEqual(saved["signal_delivered_ranks"], 2)
        self.assertEqual(saved["signal_acknowledged_ranks"], 2)
        self.assertTrue(saved["checkpoint_after_signal_verified"])
        self.assertEqual(saved["latest_checkpoint"]["step"], 5)
        self.assertEqual(self.start("101", "complete").wait(timeout=15), 0)
        resumed = self.status("101")
        self.assertTrue(resumed["resume_validated"])
        self.assertEqual(resumed["loaded_ranks"], 2)
        self.assertEqual(resumed["progressed_ranks"], 2)
        self.assertFalse(resumed["result_validated"])
        self.assertEqual(self.start("102", "complete").wait(timeout=15), 0)
        self.assertEqual(self.status("102")["state"], "skipped_completed")

    def test_missing_one_rank_proof_and_corrupt_checkpoint_never_pass(self):
        self.save_first()
        self.assertNotEqual(self.start("101", "missing").wait(timeout=15), 0)
        self.assertFalse(self.status("101")["resume_validated"])
        checkpoint = cp.generation_directory(self.root / "checkpoints", "example-run", 1)
        (checkpoint / "rank-0.json").write_bytes(b"bad")
        self.assertEqual(self.start("102", "complete").wait(timeout=15), 78)
        self.assertEqual(self.status("102")["state"], "verification_failed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
