"""Bounded, read-only snapshots for the optional terminal dashboard.

This module deliberately does not import the MCP server or open an SSH session.
An observation in this view is historical evidence, never a live cluster probe.
"""
from __future__ import annotations

import json
import hashlib
import math
import os
from pathlib import Path
import re
import sqlite3
import sys
import time

from . import __version__
from .config import config_path
from .terminal_evidence import checkpoint, progress, reports

SCHEMA = 2
MAX_JSON = 1024 * 1024
MAX_OBSERVATION = 65536
MAX_DIRECTORIES = 1000
IDENTIFIER = re.compile(r"[a-f0-9]{32}\Z")


def text(value: object, limit: int = 180) -> str:
    """Remove terminal controls, bidi controls and unbounded remote strings."""
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return ""
    return "".join(char if char.isprintable() else " " for char in str(value))[:limit].strip()


def timestamp(value: object) -> float | None:
    try:
        if type(value) in (int, float) and math.isfinite(value) and value > 0:
            return float(value)
    except OverflowError:
        pass
    return None


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("rb") as stream:
        raw = stream.read(MAX_JSON + 1)
    if len(raw) > MAX_JSON:
        raise ValueError("Fichier local trop volumineux")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Objet JSON attendu")
    return value


def registry_path() -> Path:
    return Path(os.environ.get("ROMEO_MCP_DB", str(Path.home() / ".romeo-mcp/jobs.db"))).expanduser().absolute()


def read_jobs(path: Path, limit: int, warnings: list[str]) -> list[dict]:
    if not path.is_file():
        return []
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0.2)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        has_observations = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='job_observations'").fetchone()
        observation = ("o.observed_at, substr(o.payload, 1, ?) AS payload, "
                       "substr(c.payload, 1, ?) AS checkpoint_payload"
                       if has_observations else "NULL AS observed_at, NULL AS payload, "
                       "NULL AS checkpoint_payload")
        join = ("LEFT JOIN job_observations o ON o.rowid = "
                "(SELECT rowid FROM job_observations WHERE job_id=j.job_id AND payload NOT LIKE '%\"service_id\":%' "
                "ORDER BY observed_at DESC, rowid DESC LIMIT 1) "
                "LEFT JOIN job_observations c ON c.rowid = "
                "(SELECT rowid FROM job_observations WHERE job_id=('checkpoint:' || j.job_id) "
                "ORDER BY observed_at DESC, rowid DESC LIMIT 1)" if has_observations else "")
        rows = connection.execute(
            f"SELECT j.job_id, j.name, j.partition, j.submitted_at, j.last_state, {observation} "
            f"FROM jobs j {join} ORDER BY j.submitted_at DESC, j.job_id DESC LIMIT ?",
            (MAX_OBSERVATION + 1, MAX_OBSERVATION + 1, limit) if has_observations else (limit,)).fetchall()
        result = []
        for row in rows:
            payload = {}
            if row["payload"]:
                try:
                    if len(row["payload"]) > MAX_OBSERVATION:
                        raise ValueError()
                    payload = json.loads(row["payload"])
                    if (not isinstance(payload, dict) or payload.get("job_id") != row["job_id"]
                            or payload.get("ok") is not True):
                        raise ValueError()
                except (ValueError, TypeError):
                    payload = {}
                    warnings.append("Une observation de job est illisible ou ne correspond pas au job.")
            checkpoint_info = None
            try:
                checkpoint_info = checkpoint(row["checkpoint_payload"], row["job_id"])
            except (ValueError, TypeError, KeyError):
                warnings.append("Une observation de checkpoint est illisible ou associee a un autre calcul.")
            result.append({
                "id": text(row["job_id"]), "name": text(row["name"]),
                "partition": text(row["partition"]),
                "state": text(payload.get("state") or row["last_state"] or "UNKNOWN"),
                "submitted_at": timestamp(row["submitted_at"]),
                "observed_at": timestamp(row["observed_at"]) if payload else None,
                "elapsed": text(payload.get("elapsed")), "remaining": text(payload.get("remaining")),
                "exit_code": text(payload.get("exit_code")),
                "result_validated": payload.get("result_validated") is True,
                "checkpoint": checkpoint_info,
            })
        return result
    finally:
        connection.close()


def read_transfers(root: Path, limit: int, warnings: list[str]) -> list[dict]:
    if not root.is_dir():
        return []
    candidates = []
    with os.scandir(root) as entries:
        for index, entry in enumerate(entries):
            if index >= MAX_DIRECTORIES:
                warnings.append("Inventaire des transferts limité aux 1 000 premières entrées locales.")
                break
            if IDENTIFIER.fullmatch(entry.name) and entry.is_dir(follow_symlinks=False):
                candidates.append((entry.stat(follow_symlinks=False).st_mtime, Path(entry.path)))
    result = []
    for _, directory in sorted(candidates, reverse=True)[:limit]:
        try:
            plan = read_json(directory / "plan.json")
            status = read_json(directory / "status.json")
            if plan.get("id") != directory.name or (status and status.get("transfer_id") != directory.name):
                raise ValueError()
            keys = ("id", "direction", "local_path", "remote_path", "recursive", "verify", "target", "created_at")
            sealed = hashlib.sha256(json.dumps({key: plan[key] for key in keys}, sort_keys=True).encode()).hexdigest()
            if plan.get("sha256") != sealed:
                raise ValueError()
            result.append({
                "id": directory.name, "name": text(plan.get("local_path")),
                "direction": text(plan.get("direction")), "state": text(status.get("state", "prepared")),
                "phase": text(status.get("phase")),
                "observed_at": timestamp(status.get("heartbeat_at")),
                "local_path": text(plan.get("local_path")), "remote_path": text(plan.get("remote_path")),
                "result_validated": status.get("ok") is True and status.get("result_validated") is True,
                "cancel_requested": (directory / "cancel.json").is_file(),
                "progress": progress(status),
            })
        except (OSError, ValueError, TypeError, KeyError):
            warnings.append("Un dossier de transfert est incomplet ou illisible.")
    return result


def read_updates(warnings: list[str]) -> dict:
    from . import updates
    from .update_service import overview
    result = {"version": __version__, "next_version": __version__, "latest_version": "",
              "checked_at": None, "automatic_enabled": False, "restart_required": False,
              "state": "unknown", "phase": "", "observed_at": None, "update_available": None}
    try:
        target = updates.installation()
        info = overview(target)  # Reads existing state/policy; no locks, writes or network.
        result.update(next_version=info["next_start_version"], automatic_enabled=info["automatic_enabled"],
                      restart_required=info["restart_required"], state="idle")
        cached = read_json(target.root / "check.json")
        if cached.get("schema") == 2:
            result["checked_at"] = timestamp(cached.get("checked_at"))
            release = cached.get("release")
            if isinstance(release, dict) and not cached.get("error"):
                latest = release.get("version")
                newer = updates.version_tuple(latest) > updates.version_tuple(__version__)
                result.update(latest_version=text(latest), update_available=newer)
            elif cached.get("error"):
                warnings.append("Le dernier contrôle GitHub a échoué ; disponibilité inconnue.")
        operation = read_json(target.root / "operation.json").get("operation_id", "")
        if operation:
            if not isinstance(operation, str) or not IDENTIFIER.fullmatch(operation):
                raise ValueError()
            status = read_json(target.root / "operations" / operation / "status.json")
            if status.get("operation_id") != operation:
                raise ValueError()
            result.update(state=text(status.get("state", "unknown")), phase=text(status.get("phase")),
                          observed_at=timestamp(status.get("updated_at")))
    except (OSError, ValueError, TypeError, KeyError):
        warnings.append("État local des mises à jour incomplet ou illisible.")
    return result


def snapshot(*, db: Path | None = None, limit: int = 40, demo: bool = False) -> dict:
    if not 1 <= limit <= 100:
        raise ValueError("La limite doit être comprise entre 1 et 100")
    if demo:
        return demo_snapshot(limit)
    warnings: list[str] = []
    path = (db or registry_path()).expanduser().absolute()
    jobs, transfers = [], []
    try:
        jobs = read_jobs(path, limit, warnings)
    except (OSError, sqlite3.Error):
        warnings.append("Registre local indisponible ; les jobs ne peuvent pas être affichés.")
    try:
        transfers = read_transfers(path.parent / "transfers", limit, warnings)
    except OSError:
        warnings.append("Inventaire local des transferts indisponible.")
    configured, profile = False, "full"
    try:
        config = read_json(config_path())
        from .config import FIELDS
        if any(key not in FIELDS or not isinstance(value, str) for key, value in config.items()):
            raise ValueError()
        configured = bool(os.environ.get("ROMEO_ACCOUNT", config.get("ROMEO_ACCOUNT", "")))
        profile = os.environ.get("ROMEO_TOOL_PROFILE", config.get("ROMEO_TOOL_PROFILE", "full"))
        if profile not in {"essential", "full", "expert"}:
            raise ValueError()
    except (OSError, ValueError, TypeError):
        profile = "unknown"
        warnings.append("Configuration locale illisible.")
    update = read_updates(warnings)
    report = {"automatic_enabled": None, "items": []}
    try:
        report = reports(limit)
    except (OSError, ValueError, TypeError, KeyError):
        warnings.append("Historique local des rapports inaccessible ; consulter mcp_issue_status.")
    return {"schema": SCHEMA, "generated_at": time.time(), "demo": False,
            "runtime": {"version": __version__, "profile": profile, "configured": configured,
                        "registry_present": path.is_file()},
            "jobs": jobs, "transfers": transfers, "updates": update, "reports": report,
            "warnings": list(dict.fromkeys(warnings))}


def demo_snapshot(limit: int = 40) -> dict:
    """Synthetic data only: demonstration must never read the user's files."""
    now = time.time()
    jobs = []
    for index, (name, state, age) in enumerate((
        ("Simulation MPI", "RUNNING", 12), ("Analyse OpenMP", "PENDING", 45),
        ("Prétraitement", "COMPLETED", 180), ("Simulation à reprendre", "TIMEOUT", 600))):
        jobs.append({"id": str(42001 + index), "name": name, "partition": "cpu",
                     "state": state, "submitted_at": now - 3600 - index * 600,
                     "observed_at": now - age,
                     "elapsed": "00:24:10" if state in {"RUNNING", "TIMEOUT"} else "00:02:00" if state == "COMPLETED" else "",
                     "remaining": "01:35:50" if state == "RUNNING" else "",
                     "exit_code": "0:0" if state == "COMPLETED" else "", "result_validated": False,
                     "checkpoint": ({"generation": 7, "step": 1200, "world_size": 8,
                                     "integrity_verified": True, "resume_validated": False,
                                     "signal_verified": True, "observed_at": now - 600}
                                    if state == "TIMEOUT" else None)})
    return {"schema": SCHEMA, "generated_at": now, "demo": True,
            "runtime": {"version": __version__, "profile": "full", "configured": True, "registry_present": True},
            "jobs": jobs[:limit], "transfers": [
                {"id": "a" * 32, "name": "results.tar", "direction": "download", "state": "running",
                 "phase": "transferring", "observed_at": now - 2, "local_path": "results.tar",
                 "remote_path": "simulation/results.tar", "result_validated": False, "cancel_requested": False,
                 "progress": {"bytes_transferred": 48 * 1024 ** 2, "bytes_total": 120 * 1024 ** 2,
                              "bytes_per_second": 4 * 1024 ** 2, "eta_seconds": 18, "observed_at": now - 2}},
                {"id": "b" * 32, "name": "checkpoint.bin", "direction": "upload", "state": "completed",
                 "phase": "", "observed_at": now - 90, "local_path": "checkpoint.bin",
                 "remote_path": "simulation/checkpoint.bin", "result_validated": True, "cancel_requested": False,
                 "progress": {"bytes_transferred": 8 * 1024 ** 2, "bytes_total": 8 * 1024 ** 2,
                              "bytes_per_second": None, "eta_seconds": 0, "observed_at": now - 90}},
            ][:limit],
            "updates": {"version": __version__, "next_version": __version__, "latest_version": "1.4.1",
                        "checked_at": now - 1800, "automatic_enabled": False, "restart_required": False,
                        "state": "idle", "phase": "", "observed_at": None, "update_available": True},
            "reports": {"automatic_enabled": True, "items": [
                {"id": "c" * 32, "summary": "Filtre d'une vue a corriger", "state": "local_only",
                 "category": "bug", "issue_url": "", "issue_number": None, "observed_at": now - 120,
                 "occurrences": 2, "result_validated": False, "retry_after": 0},
            ]}, "warnings": []}


def bridge() -> None:
    """One JSON response per request; EOF ends the private dashboard subprocess."""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--db", type=Path)
    parser.add_argument("--limit", type=int, default=40)
    args = parser.parse_args()
    while line := sys.stdin.readline(65):
        if line.strip() != "snapshot":
            return
        print(json.dumps(snapshot(db=args.db, limit=args.limit, demo=args.demo),
                         ensure_ascii=True, allow_nan=False), flush=True)
