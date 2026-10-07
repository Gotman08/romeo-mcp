"""Supervision autonome d'une tentative ; les signaux MPI passent par srun.

Ce processus vit dans le job, pas dans la connexion SSH du client. Toutes les
preuves sont publiees atomiquement sur stockage persistant.
"""
from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

try:
    from . import checkpoint_protocol as protocol
    from .checkpoint_storage import protect
    from .parallel_runtime import verify_mpi
except ImportError:
    import checkpoint_protocol as protocol
    from checkpoint_storage import protect
    from parallel_runtime import verify_mpi


@contextlib.contextmanager
def run_lease(directory):
    """Verrou OS : libere meme apres SIGKILL, sans supprimer le travail precedent."""
    directory = protocol.no_symlinks(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with protocol.no_symlinks(directory / ".active.lock").open("a+b") as stream:
        os.chmod(stream.name, 0o600)
        if os.name == "nt":
            import msvcrt
            stream.write(b"0")
            stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError("Une autre tentative utilise deja ce calcul ; aucun lancement concurrent") from exc
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def forward(child, signum):
    if child.poll() is not None:
        return False
    try:
        if os.name == "nt":
            child.send_signal(signum)
        else:
            os.killpg(child.pid, signum)
        return True
    except ProcessLookupError:
        return False


def stop(child):
    if child is None or child.poll() is not None:
        return
    forward(child, signal.SIGTERM)
    try:
        child.wait(timeout=10)
    except subprocess.TimeoutExpired:
        forward(child, signal.SIGKILL)
        child.wait(timeout=10)


def rank_main(config, context_path):
    """Chaque rang protege la transmission au groupe de son application."""
    context = protocol.read_json(context_path)
    rank = protocol.integer(int(os.environ.get("SLURM_PROCID", "0")), 0, context["world_size"] - 1)
    attempt = str(Path(context_path).parent)
    os.environ.update(ROMEO_CHECKPOINT_ATTEMPT=attempt, ROMEO_CHECKPOINT_RANK=str(rank),
                      ROMEO_RUN_ID=context["run_id"], ROMEO_CHECKPOINT_DIR=config["checkpoint_dir"],
                      ROMEO_RESUME_MANIFEST=context.get("checkpoint_path") or "",
                      ROMEO_RESUME_SHA256=context.get("checkpoint_sha256") or "",
                      ROMEO_RESUME_STEP=str(context.get("checkpoint_step") if context.get("checkpoint_step") is not None else -1))
    pending, child = [], None
    def receive(signum, _frame):
        pending.append(signum)
    signal.signal(signal.SIGUSR1, receive)
    signal.signal(signal.SIGTERM, receive)
    # Les descripteurs PMI transmis par Slurm doivent parvenir a MPI_Init.
    child = subprocess.Popen(["bash", "-c", "trap ':' USR1 TERM\n" + config["command"]],
                             start_new_session=True, close_fds=False)
    try:
        while child.poll() is None:
            while pending:
                signum = pending.pop(0)
                delivered = forward(child, signum)
                if signum == signal.SIGUSR1 and delivered:
                    request = protocol.read_json(Path(attempt) / "signal.json")
                    proof = {**{k: context[k] for k in ("attempt_id", "run_id", "job_id", "binding_sha256", "checkpoint_sha256")},
                             "kind": "signal_delivered", "rank": rank, "step": 0,
                             "request_id": request["request_id"], "observed_at": time.time()}
                    protocol.atomic_json(Path(attempt) / "receipts" / ("signal_delivered-%d.json" % rank), proof)
            time.sleep(0.1)
        return child.returncode
    finally:
        stop(child)


def checkpoint_summary(checkpoint):
    if checkpoint is None:
        return None
    manifest = checkpoint["manifest"]
    return {**{key: checkpoint[key] for key in ("manifest_path", "manifest_sha256", "directory", "bytes", "integrity_verified")},
            **{key: manifest[key] for key in ("run_id", "generation", "step", "world_size", "binding_sha256")}}


def signal_evidence(evidence, latest, request, world):
    if request is None:
        return {}
    acknowledgements = [r for r, v in evidence["receipts"]["signal_ack"].items() if v.get("request_id") == request["request_id"]]
    deliveries = [r for r, v in evidence["receipts"]["signal_delivered"].items() if v.get("request_id") == request["request_id"]]
    coherent = latest and latest["manifest"].get("signal_request_id") == request["request_id"]
    coherent = coherent and len(acknowledgements) == world and all(
        evidence["receipts"]["signal_ack"][r]["step"] == latest["manifest"]["step"] for r in acknowledgements)
    return {"signal_acknowledged_ranks": len(acknowledgements), "signal_delivered_ranks": len(deliveries),
            "checkpoint_after_signal_verified": bool(coherent)}


def completed_before(run, binding, world):
    marker = run / "completion.json"
    if not marker.exists():
        return False
    value = protocol.read_json(marker)
    if value.get("binding_sha256") != protocol.digest(binding) or value.get("world_size") != world:
        return False
    attempt = run / "attempts" / protocol.identity(value.get("attempt_id"))
    context = protocol.read_json(attempt / "context.json")
    if any(context.get(key) != value.get(key) for key in ("binding_sha256", "world_size", "attempt_id", "job_id")):
        return False
    previous = protocol.read_json(attempt / "status.json")
    receipts = protocol.observe_receipts(attempt, context)
    return (previous.get("exit_code") == 0 and receipts["application_completion_observed"]
            and (context.get("checkpoint_step") is None or receipts["resume_validated"]))


def supervise(config):
    contract = config["contract"]
    root, run_id = Path(config["checkpoint_dir"]), contract["run_id"]
    run = protocol.no_symlinks(root / run_id)
    run.mkdir(parents=True, exist_ok=True, mode=0o700)
    job_id = protocol.identity(os.environ.get("SLURM_JOB_ID", "local"))
    attempt_id = uuid.uuid4().hex
    attempt = run / "attempts" / attempt_id
    attempt.mkdir(parents=True, mode=0o700)
    pending = {"save": False, "terminate": False}
    signal.signal(signal.SIGUSR1, lambda *_: pending.update(save=True))
    signal.signal(signal.SIGTERM, lambda *_: pending.update(terminate=True))
    state = {"schema": "romeo-runtime-observation-v1", "run_id": run_id, "job_id": job_id,
             "attempt_id": attempt_id, "world_size": contract["world_size"], "state": "initializing",
             "resume_validated": False, "result_validated": False, "application_completion_observed": False,
             "checkpoint_integrity_verified": False, "signal_requested": False, "signal_acknowledged_ranks": 0,
             "signal_delivered_ranks": 0, "checkpoint_after_signal_verified": False}
    def persist(**updates):
        state.update(**updates, observed_at=time.time(), heartbeat_at=time.time())
        protocol.atomic_json(attempt / "status.json", state)
        protocol.atomic_json(run / "jobs" / (job_id + ".json"), state)
    persist()
    child = None
    try:
        with run_lease(run):
            if contract["action"] == "protect":
                selection = protocol.discover(root, run_id, world_size=contract["world_size"],
                                              max_bytes=contract["max_checkpoint_bytes"], timeout=contract["verification_timeout_seconds"],
                                              expected_binding_sha256=contract.get("expected_binding_sha256"))
                latest = selection["checkpoint"]
                if latest is None:
                    raise ValueError("Aucun checkpoint complet associe au job source a proteger")
                quota = {"filesystem": contract["quota_filesystem"], "fileset": contract["quota_fileset"], "group": contract.get("quota_group")}
                protection = protect(latest, root, contract["backup_dir"], quota, contract["keep_last"], contract["verification_timeout_seconds"])
                persist(state="protected", checkpoint=checkpoint_summary(latest), latest_checkpoint=checkpoint_summary(latest),
                        checkpoint_integrity_verified=True, binding_sha256=latest["manifest"]["binding_sha256"], protection=protection, exit_code=0)
                return 0
            mpi = verify_mpi(config["mpi_environment"], config["architecture"]) if config.get("mpi_environment") else None
            environment = {"architecture": config["architecture"],
                           "spack_hashes": sorted(filter(None, os.environ.get("SPACK_LOADED_HASHES", "").split(":"))), "mpi": mpi}
            persist(state="verifying_inputs", mpi_environment=mpi)
            binding = protocol.workload_binding(config["command"], contract["code_files"], contract["data_files"], environment,
                                                max_bytes=contract["max_input_bytes"], timeout=contract["verification_timeout_seconds"])
            persist(binding=binding, binding_sha256=protocol.digest(binding))
            if contract["action"] == "run" and completed_before(run, binding, contract["world_size"]):
                persist(state="skipped_completed", application_completion_observed=True, skipped=True, exit_code=0)
                return 0
            persist(state="verifying_checkpoint")
            selection = protocol.discover(root, run_id, binding=binding, world_size=contract["world_size"],
                                          max_bytes=contract["max_checkpoint_bytes"], timeout=contract["verification_timeout_seconds"],
                                          expected_binding_sha256=contract.get("expected_binding_sha256"))
            selected = selection["checkpoint"]
            if selected is None and (selection["generations_seen"] or contract["require_resume"] or contract["action"] == "protect"):
                raise ValueError("Aucun checkpoint complet et compatible ; refus de repartir a zero. " + str(selection["rejected"][:3]))
            context = {"attempt_id": attempt_id, "run_id": run_id, "job_id": job_id,
                       "world_size": contract["world_size"], "binding_sha256": protocol.digest(binding), "binding": binding,
                       "checkpoint_path": selected["manifest_path"] if selected else None,
                       "checkpoint_sha256": selected["manifest_sha256"] if selected else None,
                       "checkpoint_step": selected["manifest"]["step"] if selected else None}
            protocol.atomic_json(attempt / "context.json", context, immutable=True)
            os.environ.update(ROMEO_CHECKPOINT_ATTEMPT=str(attempt), ROMEO_RUN_ID=run_id,
                              ROMEO_CHECKPOINT_DIR=str(root), ROMEO_RESUME_MANIFEST=context["checkpoint_path"] or "",
                              ROMEO_RESUME_SHA256=context["checkpoint_sha256"] or "",
                              ROMEO_RESUME_STEP=str(context["checkpoint_step"] if selected else -1))
            os.environ["PYTHONPATH"] = config["runtime_directory"] + os.pathsep + os.environ.get("PYTHONPATH", "")
            os.environ["ROMEO_CHECKPOINT_HELPER"] = str(Path(config["runtime_directory"]) / "checkpoint_protocol.py")
            os.environ["ROMEO_CHECKPOINT_PYTHON"] = sys.executable
            persist(checkpoint=checkpoint_summary(selected), rejected_checkpoints=selection["rejected"][:20],
                    checkpoint_integrity_verified=selected is not None)
            latest = selected
            protected_sha = None
            def protect_latest():
                nonlocal protected_sha
                if latest and contract.get("backup_dir") and latest["manifest_sha256"] != protected_sha:
                    persist(state="protecting_checkpoint")
                    quota = {"filesystem": contract["quota_filesystem"], "fileset": contract["quota_fileset"],
                             "group": contract.get("quota_group")}
                    protection = protect(latest, root, contract["backup_dir"], quota, contract["keep_last"],
                                         contract["verification_timeout_seconds"])
                    protected_sha = latest["manifest_sha256"]
                    persist(protection=protection)
            protect_latest()
            if config["distributed"] in {"mpi", "openmp"}:
                if os.environ.get("SLURM_NTASKS") and int(os.environ["SLURM_NTASKS"]) != contract["world_size"]:
                    raise ValueError("Nombre de taches Slurm different du contrat")
                command = ["srun", "--kill-on-bad-exit=1"]
                if config.get("cpu_bind") or config["cpus_per_task"] > 1:
                    command.append("--cpu-bind=" + (config.get("cpu_bind") or "cores"))
                if config.get("gpu_bind"):
                    command.append("--gpu-bind=" + config["gpu_bind"])
                command += [sys.executable, str(Path(config["runtime_directory"]) / "checkpoint_runner.py"),
                            str(Path(config["runtime_directory"]) / "config.json"), "--rank", str(attempt / "context.json")]
            elif not config["distributed"]:
                command = [sys.executable, str(Path(config["runtime_directory"]) / "checkpoint_runner.py"),
                           str(Path(config["runtime_directory"]) / "config.json"), "--rank", str(attempt / "context.json")]
            else:
                command = ["bash", "-c", "trap ':' USR1 TERM\n" + config["launcher_command"]]
            started = time.monotonic()
            child = subprocess.Popen(command, start_new_session=True, cwd=config["workdir"])
            request = None
            next_checkpoint_check = 0.0
            receipt_cache = {}
            persist(state="awaiting_resume" if selected else "running", launcher_pid=child.pid)
            while child.poll() is None:
                if pending["terminate"]:
                    persist(state="termination_requested")
                    stop(child)
                    break
                if pending["save"]:
                    pending["save"] = False
                    request = {"request_id": uuid.uuid4().hex, "requested_at": time.time()}
                    protocol.atomic_json(attempt / "signal.json", request)
                    forwarded = forward(child, signal.SIGUSR1)
                    persist(signal_requested=True, signal_request_id=request["request_id"], signal_forwarded_to_launcher=forwarded,
                            checkpoint_after_signal_verified=False, signal_acknowledged_ranks=0, signal_delivered_ranks=0)
                evidence = protocol.observe_receipts(attempt, context, receipt_cache)
                if selected and not evidence["resume_validated"] and time.monotonic() - started > contract["resume_timeout_seconds"]:
                    raise ValueError("Reprise non prouvee par chargement et progression de tous les rangs dans le delai")
                if time.monotonic() >= next_checkpoint_check:
                    candidate = protocol.discover(root, run_id, binding=binding, world_size=contract["world_size"], verify_files=False,
                                                  max_bytes=contract["max_checkpoint_bytes"], timeout=contract["verification_timeout_seconds"])["checkpoint"]
                    if candidate and (latest is None or candidate["manifest_sha256"] != latest["manifest_sha256"]):
                        latest = protocol.verify_checkpoint(candidate["manifest_path"], binding=binding, run_id=run_id,
                                                            world_size=contract["world_size"], max_bytes=contract["max_checkpoint_bytes"],
                                                            deadline=time.monotonic() + contract["verification_timeout_seconds"])
                        protect_latest()
                    next_checkpoint_check = time.monotonic() + 5
                update = {k: v for k, v in evidence.items() if k != "receipts"}
                if request:
                    update.update(signal_evidence(evidence, latest, request, contract["world_size"]))
                persist(state="running" if not selected or evidence["resume_validated"] else "awaiting_resume",
                        latest_checkpoint=checkpoint_summary(latest), **update)
                # Les grands communicateurs ne doivent pas saturer GPFS en
                # relisant des preuves identiques a chaque demi-seconde.
                time.sleep(max(0.5, min(5.0, contract["world_size"] / 256)))
            evidence = protocol.observe_receipts(attempt, context)
            # Les programmes courts peuvent publier et quitter entre deux releves.
            candidate = protocol.discover(root, run_id, binding=binding, world_size=contract["world_size"],
                                          max_bytes=contract["max_checkpoint_bytes"], timeout=contract["verification_timeout_seconds"])["checkpoint"]
            if candidate:
                latest = candidate
                protect_latest()
            code = child.returncode if child.returncode is not None else 143
            completion = code == 0 and evidence["application_completion_observed"] and (selected is None or evidence["resume_validated"])
            effective_code = code if code else 0 if completion else 79
            persist(state="completed" if completion else "stopped", exit_code=effective_code, application_exit_code=code,
                    latest_checkpoint=checkpoint_summary(latest), **{k: v for k, v in evidence.items() if k != "receipts"},
                    **signal_evidence(evidence, latest, request, contract["world_size"]))
            if completion:
                protocol.atomic_json(run / "completion.json", {k: context[k] for k in ("attempt_id", "job_id", "world_size", "binding_sha256")})
            # Une sortie 0 sans preuves n'autorise ni fin annoncee ni segment ignore.
            return effective_code
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        stop(child)
        persist(state="verification_failed", error=str(exc)[:1000], exit_code=78)
        return 78
    finally:
        stop(child)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    config = protocol.read_json(argv[0])
    if len(argv) == 3 and argv[1] == "--rank":
        return rank_main(config, argv[2])
    if config.get("contract") is None:
        # Verification MPI demandee sans protocole de checkpoint.
        report = verify_mpi(config["mpi_environment"], config["architecture"])
        report.update(job_id=os.environ.get("SLURM_JOB_ID", "local"), observed_at=time.time(),
                      request_sha256=protocol.digest(config["mpi_environment"]), result_validated=False)
        protocol.atomic_json(Path(config["runtime_directory"]) / (os.environ.get("SLURM_JOB_ID", "local") + "-mpi.json"), report)
        return subprocess.call(["bash", "-c", config["launcher_command"]], cwd=config["workdir"])
    return supervise(config)


if __name__ == "__main__":
    raise SystemExit(main())
