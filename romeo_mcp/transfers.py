"""Single-use transfer plans and durable observations, independent of MCP transport."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

from .cluster import DEFAULT_ACCOUNT
from .guard import check_path
from .registry import registry
from .ssh import session


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            os.chmod(temporary, 0o600)
            json.dump(value, stream, ensure_ascii=False, allow_nan=False)
        for attempt in range(6):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(0.01 * (attempt + 1))
    finally:
        temporary.unlink(missing_ok=True)


def read(path):
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("Observation de transfert trop volumineuse")
    return json.loads(path.read_text(encoding="utf-8"))


def seal(plan):
    keys = ("id", "direction", "local_path", "remote_path", "recursive", "verify", "target", "created_at")
    return hashlib.sha256(json.dumps({k: plan[k] for k in keys}, sort_keys=True).encode()).hexdigest()


def load(transfer_id):
    if not isinstance(transfer_id, str) or not re.fullmatch(r"[a-f0-9]{32}", transfer_id):
        raise ValueError("transfer_id invalide")
    directory = registry().path.parent / "transfers" / transfer_id
    try:
        plan = read(directory / "plan.json")
    except (OSError, ValueError) as exc:
        raise ValueError("Plan de transfert introuvable ou illisible") from exc
    if plan.get("id") != transfer_id or plan.get("sha256") != seal(plan):
        raise ValueError("Plan de transfert altere")
    return directory, plan


def prepare(direction, local_path, remote_path, recursive=False, verify=True):
    if direction not in {"upload", "download"}:
        raise ValueError("direction doit etre upload ou download")
    local = Path(local_path).expanduser().resolve()
    if direction == "upload" and not local.exists():
        raise ValueError("Source locale absente")
    if direction == "download" and local.is_dir():
        raise ValueError("Choisis le chemin exact du fichier ou du repertoire de destination")
    connection = session()
    remote = check_path(remote_path, connection.home, connection.scratch, connection.path_aliases)
    plan = {"id": uuid.uuid4().hex, "created_at": time.time(), "direction": direction,
            "local_path": str(local), "remote_path": remote, "recursive": recursive, "verify": verify,
            "target": {"host": connection.host, "user": connection.user, "account": DEFAULT_ACCOUNT}}
    plan["sha256"] = seal(plan)
    directory = registry().path.parent / "transfers" / plan["id"]
    atomic(directory / "plan.json", plan)
    return {"ok": True, "transfer_id": plan["id"], "plan": plan, "started": False}


def start(transfer_id, confirm=False):
    if confirm is not True:
        raise ValueError("Relis le plan puis passe confirm=true")
    directory, plan = load(transfer_id)
    if time.time() - plan["created_at"] > 86400:
        raise ValueError("Plan de transfert expire")
    connection = session()
    if plan["target"] != {"host": connection.host, "user": connection.user, "account": DEFAULT_ACCOUNT}:
        raise ValueError("La cible SSH ou le compte ont change")
    try:
        descriptor = os.open(directory / "started.claim", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return {**status(transfer_id), "already_started": True, "replayed": False}
    os.close(descriptor)
    atomic(directory / "status.json", {"ok": True, "transfer_id": transfer_id, "state": "launching", "result_validated": False})
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parent.parent), "ROMEO_UPDATE_CHECK": "0"}
    startup = {}
    if os.name == "nt":
        startup["creationflags"] = subprocess.CREATE_NO_WINDOW
    else:
        startup["start_new_session"] = True
    try:
        with (directory / "worker.log").open("ab") as stream:
            child = subprocess.Popen([sys.executable, "-m", "romeo_mcp.transfer_worker", str(directory / "plan.json")],
                                     stdin=subprocess.DEVNULL, stdout=stream, stderr=stream, env=env, **startup)
    except OSError as exc:
        atomic(directory / "status.json", {"ok": False, "transfer_id": transfer_id, "state": "launchFailed", "error": str(exc)})
        raise
    return {"ok": True, "transfer_id": transfer_id, "started": True, "worker_pid": child.pid,
            "result_validated": False, "next_step": "Consulte transfer_status ; ne relance pas un autre transfert."}


def status(transfer_id, max_chars=4000):
    if not 0 <= max_chars <= 20000:
        raise ValueError("max_chars doit etre compris entre 0 et 20000")
    directory, plan = load(transfer_id)
    path = directory / "status.json"
    result = read(path) if path.is_file() else {"ok": True, "transfer_id": transfer_id,
                                             "state": "unverified" if (directory / "started.claim").exists() else "prepared",
                                             "result_validated": False}
    if result.get("transfer_id") != transfer_id:
        raise ValueError("Observation d'un autre transfert")
    heartbeat = result.get("heartbeat_at")
    terminal = result["state"] in {"completed", "completed_unverified", "failed", "cancelled", "launchFailed"}
    result.update(plan=plan, current_process_observed=False,
                  heartbeat_age_seconds=max(0, time.time() - heartbeat) if heartbeat is not None else None,
                  liveness="terminal_result" if terminal else "unverified",
                  cancel_requested=(directory / "cancel.json").exists())
    log = directory / "transfer.log"
    if log.is_file() and max_chars:
        with log.open("rb") as stream:
            stream.seek(0, 2)
            size = stream.tell()
            stream.seek(max(0, size - max_chars))
            result.update(log_tail=stream.read(max_chars).decode("utf-8", "replace"), log_truncated=size > max_chars)
    return result


def cancel(transfer_id, confirm=False):
    if confirm is not True:
        raise ValueError("L'annulation exige confirm=true")
    directory, plan = load(transfer_id)
    observed = status(transfer_id, 0)
    if observed["state"] in {"completed", "completed_unverified", "failed", "cancelled", "launchFailed"}:
        return {"ok": True, "transfer_id": transfer_id, "cancel_requested": False,
                "cancellation_observed": observed["state"] == "cancelled", "state": observed["state"]}
    if not (directory / "started.claim").exists():
        raise ValueError("Le transfert n'a pas ete demarre")
    atomic(directory / "cancel.json", {"transfer_id": transfer_id, "requested_at": time.time()})
    return {"ok": True, "transfer_id": transfer_id, "cancel_requested": True, "cancellation_observed": False,
            "partial_output_possible": True, "next_step": "Consulte transfer_status pour observer l'annulation."}
