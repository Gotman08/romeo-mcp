"""Compact evidence for the dashboard; no SSH, publication or verification IO."""
from __future__ import annotations

import json
import math
import os
import re

MAX_OBSERVATION = 65536
_SHA = re.compile(r"[a-f0-9]{64}\Z")


def number(value, *, integer=False):
    """Reject booleans, non-finite numbers and values beyond the wire contract."""
    if type(value) not in ((int,) if integer else (int, float)):
        return None
    try:
        if math.isfinite(value) and 0 <= value <= 2 ** 53:
            return value
    except OverflowError:
        pass
    return None


def checkpoint(raw, job_id):
    """Only show a saved checkpoint associated with this job, run and ranks."""
    if not raw:
        return None
    if len(raw) > MAX_OBSERVATION:
        raise ValueError("Observation de checkpoint trop volumineuse")
    value = json.loads(raw)
    if (not isinstance(value, dict) or value.get("job_id") != job_id
            or value.get("schema") != "romeo-runtime-observation-v1"):
        raise ValueError("Observation de checkpoint d'un autre job")
    latest = value.get("latest_checkpoint") or value.get("checkpoint")
    if latest is None:
        return None
    if not isinstance(latest, dict):
        raise ValueError("Checkpoint illisible")
    world = number(value.get("world_size"), integer=True)
    binding = value.get("binding_sha256")
    manifest = latest.get("manifest_sha256")
    if (not world or number(latest.get("world_size"), integer=True) != world
            or not isinstance(value.get("run_id"), str) or not value["run_id"]
            or latest.get("run_id") != value["run_id"]
            or not isinstance(binding, str) or not _SHA.fullmatch(binding)
            or latest.get("binding_sha256") != binding
            or not isinstance(manifest, str) or not _SHA.fullmatch(manifest)):
        raise ValueError("Association du checkpoint absente ou incoherente")
    generation, step = (number(latest.get(key), integer=True) for key in ("generation", "step"))
    if generation is None or step is None:
        raise ValueError("Generation ou etape du checkpoint invalide")
    verified = latest.get("integrity_verified") is True
    return {"generation": generation, "step": step, "world_size": world,
            "integrity_verified": verified, "resume_validated": value.get("resume_validated") is True,
            "observed_at": number(value.get("observed_at")) or None,
            "signal_verified": value.get("checkpoint_after_signal_verified") is True}


def progress(status):
    """Only measured byte totals or a recorded transport percentage are useful."""
    value = status.get("progress")
    if not isinstance(value, dict):
        return None
    done = number(value.get("bytes_transferred"), integer=True)
    total = number(value.get("bytes_total"), integer=True)
    percent = number(value.get("percent_reported"), integer=True)
    observed = number(value.get("observed_at"))
    if done is None or not observed:
        return None
    if total is not None:
        if not total or done > total:
            return None
        percent = None
    elif (value.get("bytes_total") is not None or value.get("source") != "rsync_progress2"
          or percent is None or percent > 100):
        return None
    return {"bytes_transferred": done, "bytes_total": total,
            "percent_reported": percent,
            "bytes_per_second": number(value.get("bytes_per_second")),
            "eta_seconds": number(value.get("eta_seconds")), "observed_at": observed}


def reports(limit):
    """Read sealed, already sanitized reports without credentials or HTTP calls."""
    from .issue_store import ReportStore
    from .updates import REPOSITORY
    store = ReportStore()
    saved = store.policy()
    override = os.environ.get("ROMEO_AUTO_ISSUES")
    automatic = saved["saved_automatic"]
    if override is not None:
        if override.lower() not in {"0", "1", "false", "true", "off", "on"}:
            raise ValueError("Autorisation des rapports illisible")
        automatic = override.lower() in {"1", "true", "on"}
    items = []
    for row in store.recent(limit):
        document = row["report"]
        summary = document.get("summary")
        if not isinstance(summary, str) or len(summary) > 160:
            raise ValueError("Resume de rapport illisible")
        # Failed/uncertain records need not contain a canonical GitHub URL.
        # Never display an arbitrary URL or query string saved in their metadata.
        issue_number = number(row.get("issue_number"), integer=True)
        issue_url = row.get("issue_url")
        if not issue_number or issue_url != f"https://github.com/{REPOSITORY}/issues/{issue_number}":
            issue_number, issue_url = None, ""
        items.append({"id": row["report_id"], "summary": summary, "state": row["state"],
                      "category": document.get("category", "bug"), "issue_url": issue_url,
                      "issue_number": issue_number, "observed_at": number(row["updated_at"]),
                      "occurrences": number(row["occurrences"], integer=True) or 0,
                      "result_validated": row["result_validated"],
                      "retry_after": number(row.get("retry_after")) or 0})
    return {"automatic_enabled": automatic, "items": items}
