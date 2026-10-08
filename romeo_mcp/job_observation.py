"""Slurm observations and evidence semantics, independent of MCP registration."""
from __future__ import annotations
import re
import shlex
from .slurm import TERMINAL_STATES

def _error(message, **extra):
    return {"ok": False, "error": message, **extra}

def status_command(jid):
    if not re.fullmatch(r"\d+(?:_(?:\d+|\[[\d,:%-]+\]))?", jid):
        raise ValueError("Identifiant Slurm invalide")
    quoted = shlex.quote(jid)
    # Query accounting only after leaving the queue; estimated start only for pending jobs.
    return (
        "live=$(squeue -h -j {jid} -o '%i|%j|%P|%T|%M|%L|%D|%R|%E') || exit $?; "
        "printf '###LIVE\n%s\n' \"$live\"; "
        "if [ -n \"$live\" ]; then echo '###START'; "
        "case \"$live\" in *'|PENDING|'*) squeue -h -j {jid} --start -o '%S' || exit $?;; esac; "
        "else echo '###PAST'; sacct -j {jid} -X -n -P "
        "-o JobID,JobName,Partition,State,Elapsed,ExitCode,Start,End || exit $?; fi"
    ).format(jid=quoted)

def parse_status(text, jid):
    sections: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        if line.startswith("###"):
            current = line[3:].strip()
            sections[current] = []
        elif current and line.strip():
            sections[current].append(line.strip())

    live = sections.get("LIVE", [])
    if live:
        parts = live[0].split("|")
        if len(parts) < 8 or (parts[0].strip() != jid and not parts[0].strip().startswith(jid + "_")) or not parts[3].strip():
            return _error("Observation Slurm malformee ou d'un autre job", job_id=jid)
        state = parts[3].strip() if len(parts) > 3 else "?"
        start = sections.get("START", [""])[0] if sections.get("START") else ""
        return {
            "ok": True,
            "job_id": jid,
            "allocation_id": parts[0].strip(),
            "scope": "job" if parts[0].strip() == jid else "matching_allocation",
            "finished": False,
            "scheduler_completed": False, "result_validated": False,
            "name": parts[1].strip() if len(parts) > 1 else "",
            "partition": parts[2].strip() if len(parts) > 2 else "",
            "state": state,
            "elapsed": parts[4].strip() if len(parts) > 4 else "",
            "remaining": parts[5].strip() if len(parts) > 5 else "",
            "nodes": parts[6].strip() if len(parts) > 6 else "",
            "reason_or_nodelist": parts[7].strip() if len(parts) > 7 else "",
            "dependencies_remaining": (
                "" if parts[8].strip().lower() in {"", "null", "(null)", "n/a"} else parts[8].strip()
            ) if len(parts)>8 and len(parts[8])<=1000 and re.fullmatch(r"[A-Za-z0-9_:,?()%-]*",parts[8].strip()) else None,
            "estimated_start": start or None,
        }

    past = [line for line in sections.get("PAST", []) if line.split("|", 1)[0].strip() == jid]
    if past:
        parts = past[0].split("|")
        if len(parts) < 8 or not parts[3].strip():
            return _error("Observation comptable Slurm malformee", job_id=jid)
        state = parts[3].strip() if len(parts) > 3 else "?"
        return {
            "ok": True,
            "job_id": jid,
            "finished": state.split()[0].rstrip("+") in TERMINAL_STATES,
            "scheduler_completed": state.split()[0].rstrip("+") == "COMPLETED",
            "scheduler_success_observed": state.split()[0].rstrip("+") == "COMPLETED" and parts[5].strip() == "0:0",
            "result_validated": False,
            "name": parts[1].strip() if len(parts) > 1 else "",
            "partition": parts[2].strip() if len(parts) > 2 else "",
            "state": state,
            "elapsed": parts[4].strip() if len(parts) > 4 else "",
            "exit_code": parts[5].strip() if len(parts) > 5 else "",
            "start": parts[6].strip() if len(parts) > 6 else "",
            "end": parts[7].strip() if len(parts) > 7 else "",
            "next_step": "Consulte job_log_tail puis job_efficiency.",
        }

    return _error(
        "job {} inconnu de SLURM. Verifie l'identifiant, ou l'historique a "
        "peut-etre ete purge.".format(jid),
        job_id=jid,
    )
