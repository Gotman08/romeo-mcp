"""Validation et fichiers scelles des jobs a checkpoints, sans transport MCP."""
from __future__ import annotations

import hashlib
import json
import posixpath
import re
import shlex
import uuid
from pathlib import Path

from .checkpoint_protocol import identity, integer
from .privacy import sensitive_path

RUNTIME_MODULES = ("checkpoint_protocol.py", "checkpoint_storage.py", "parallel_runtime.py", "checkpoint_runner.py")
CONTRACT_KEYS = {"run_id", "code_files", "data_files", "world_size", "require_resume", "backup_dir",
                 "quota_fileset", "quota_filesystem", "quota_group", "keep_last", "max_checkpoint_bytes",
                 "max_input_bytes", "verification_timeout_seconds", "resume_timeout_seconds", "runtime_python", "action",
                 "expected_binding_sha256"}


def normalize_contract(contract, spec, arch):
    if not isinstance(contract, dict) or set(contract) - CONTRACT_KEYS:
        raise ValueError("checkpoint_contract contient des champs inconnus")
    result = {"run_id": uuid.uuid4().hex, "data_files": [], "require_resume": False,
              "keep_last": 3, "max_checkpoint_bytes": 2**40, "max_input_bytes": 2**40,
              "verification_timeout_seconds": 900, "resume_timeout_seconds": 120,
              "runtime_python": "python3", "action": "run", **contract}
    identity(result["run_id"])
    if result.get("expected_binding_sha256") is not None and not re.fullmatch(r"[a-f0-9]{64}", str(result["expected_binding_sha256"])):
        raise ValueError("expected_binding_sha256 invalide")
    world = spec.nodes * (spec.gpus_per_node if spec.distributed in {"ddp", "accelerate", "deepspeed", "srun"}
                          else spec.ntasks_per_node if spec.distributed else 1)
    integer(result.setdefault("world_size", world), 1, 16384)
    if result["action"] not in {"run", "protect"}:
        raise ValueError("Action de checkpoint inconnue")
    if result["action"] == "run" and result["world_size"] != world:
        raise ValueError("world_size doit correspondre a la topologie du lanceur")
    if spec.nodes > 1 and not spec.distributed:
        raise ValueError("Checkpoint multi-noeuds : choisir un lanceur distribue explicite")
    if type(result["require_resume"]) is not bool:
        raise ValueError("require_resume doit etre un booleen")
    code, data = result.get("code_files"), result["data_files"]
    if not isinstance(code, list) or not code or not isinstance(data, list) or len(code) + len(data) > 128:
        raise ValueError("checkpoint_contract : declarer 1 a 128 fichiers de programme/donnees (code_files obligatoire)")
    for path in code + data + ([result["backup_dir"]] if result.get("backup_dir") else []):
        if not isinstance(path, str) or not path.startswith("/") or any(c in path for c in "\n\x00") or sensitive_path(path):
            raise ValueError("Chemin absolu non sensible requis dans le contrat")
    if len(set(code + data)) != len(code + data):
        raise ValueError("Fichiers de programme/donnees dupliques")
    integer(result["keep_last"], 2, 100)
    for field in ("max_checkpoint_bytes", "max_input_bytes"):
        integer(result[field], 1, 2**50)
    integer(result["verification_timeout_seconds"], 1, 14400)
    integer(result["resume_timeout_seconds"], 1, 3600)
    if not isinstance(result["runtime_python"], str) or not re.fullmatch(r"(?:/[A-Za-z0-9_./+-]+|python3(?:\.[0-9]+)?)", result["runtime_python"]):
        raise ValueError("runtime_python attend python3 ou un chemin absolu d'interpreteur")
    if result.get("backup_dir"):
        for field in ("quota_fileset", "quota_filesystem", "quota_group"):
            if field == "quota_filesystem":
                result.setdefault(field, "gpfs")
            value = result.get(field)
            if field == "quota_group" and not value:
                continue
            if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", value):
                raise ValueError("La copie exige un %s exact, obtenu avec romeo_quota" % field)
        if spec.checkpoint_dir and posixpath.normpath(result["backup_dir"]) == posixpath.normpath(spec.checkpoint_dir):
            raise ValueError("backup_dir doit differer de checkpoint_dir")
    if not spec.checkpoint_dir:
        raise ValueError("Un contrat de checkpoint exige checkpoint_dir")
    return result


def runtime_directory(spec, workdir):
    if not spec.runtime_id:
        spec.runtime_id = uuid.uuid4().hex
    identity(spec.runtime_id)
    return posixpath.join(workdir, ".romeo-runtime", spec.runtime_id)


def runtime_configuration(spec, workdir, arch):
    from .templates import enveloppe_conteneur, lanceur_distribue, options_affinite
    command = spec.command.strip()
    if spec.container:
        command = enveloppe_conteneur(spec.container, command, spec.container_binds)
    launched = command
    if spec.distributed:
        launched = lanceur_distribue(spec.distributed, command, spec.gpus_per_node,
                                    options_affinite(spec.cpus_per_task, spec.cpu_bind))
    return {"schema": "romeo-runtime-v1", "command": command, "launcher_command": launched,
            "workdir": workdir, "architecture": arch, "contract": spec.checkpoint_contract,
            "checkpoint_dir": spec.checkpoint_dir, "distributed": spec.distributed,
            "cpu_bind": spec.cpu_bind, "cpus_per_task": spec.cpus_per_task,
            "gpu_bind": spec.gpu_bind, "mpi_environment": spec.mpi_environment,
            "runtime_directory": runtime_directory(spec, workdir)}


def runtime_files(plan):
    if plan.spec.checkpoint_contract is None and plan.spec.mpi_environment is None:
        return []
    directory = runtime_directory(plan.spec, plan.workdir)
    files = [{"path": posixpath.join(directory, name),
              "content": (Path(__file__).parent / name).read_text(encoding="utf-8")}
             for name in RUNTIME_MODULES]
    config = runtime_configuration(plan.spec, plan.workdir, plan.arch)
    files.append({"path": posixpath.join(directory, "config.json"),
                  "content": json.dumps(config, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"})
    for item in files:
        item["sha256"] = hashlib.sha256(item["content"].encode()).hexdigest()
    return files


def runtime_fragment(spec, workdir, arch):
    from .slurm import Plan
    files = runtime_files(Plan(spec, 0, "", arch, workdir, "", []))
    directory = runtime_directory(spec, workdir)
    python = (spec.checkpoint_contract or {}).get("runtime_python", "python3")
    # Montrer la commande et conserver les controles de secrets du script.
    lines = ["# Commande applicative : " + line for line in spec.command.splitlines()]
    lines += ["# Fichiers exacts revus et scelles pendant la preparation.", "sha256sum --check <<'ROMEO_RUNTIME_SHA256'"]
    lines += [item["sha256"] + "  " + item["path"] for item in files]
    lines += ["ROMEO_RUNTIME_SHA256", "ROMEO_SUPERVISOR_PID=", "ROMEO_SIGNAL_PENDING=0",
              "_romeo_checkpoint_signal() {",
              '  if [ -n "$ROMEO_SUPERVISOR_PID" ]; then kill -USR1 "$ROMEO_SUPERVISOR_PID" 2>/dev/null || true;',
              "  else ROMEO_SIGNAL_PENDING=1; fi", "}", "trap _romeo_checkpoint_signal USR1",
              'trap \'if [ -n "$ROMEO_SUPERVISOR_PID" ]; then kill -TERM "$ROMEO_SUPERVISOR_PID" 2>/dev/null || true; fi\' TERM',
              "%s %s %s &" % (shlex.quote(python), shlex.quote(posixpath.join(directory, "checkpoint_runner.py")),
                               shlex.quote(posixpath.join(directory, "config.json"))),
              "ROMEO_SUPERVISOR_PID=$!", 'if [ "$ROMEO_SIGNAL_PENDING" -eq 1 ]; then _romeo_checkpoint_signal; fi',
              "set +e", 'wait "$ROMEO_SUPERVISOR_PID"; ROMEO_EXIT=$?',
              'while [ "$ROMEO_EXIT" -gt 128 ] && kill -0 "$ROMEO_SUPERVISOR_PID" 2>/dev/null; do',
              '  wait "$ROMEO_SUPERVISOR_PID"; ROMEO_EXIT=$?', "done", "set -e", 'exit "$ROMEO_EXIT"']
    return lines
