"""Slurm observations and evidence semantics, independent of MCP registration."""
from __future__ import annotations
import re
import shlex
from .slurm import TERMINAL_STATES

#: Champs du releve `squeue` d'un job. `%S` est le demarrage reel, ou estime
#: pour un job en attente : `squeue --start` n'est qu'un format et un filtre
#: autour de ce meme champ. Le lire ici evite une seconde requete au
#: controleur a chaque sondage d'un job en attente. `%C` et `%m` (coeurs et
#: memoire) evitent de meme un second `squeue` aux outils de telemetrie.
LIVE_FORMAT = "%i|%j|%P|%T|%M|%L|%D|%R|%E|%S|%C|%m"

#: Age maximal par defaut d'une observation reutilisee pour un job encore
#: vivant. Un meme tour lit souvent un job plusieurs fois (job_status puis
#: job_live_metrics, diagnose_job, wait_for_job) et plusieurs sessions peuvent
#: suivre le meme job : chaque relecture serait une requete Slurm de plus.
LIVE_REUSE_SECONDS = 20
MAX_REUSE_SECONDS = 300

#: Etats que Slurm ne modifie plus : leur observation reste valable sans limite
#: d'age. PREEMPTED, NODE_FAIL et BOOT_FAIL en sont exclus, car Slurm peut
#: remettre le job en file, ou il redevient PENDING.
STABLE_FINAL_STATES = frozenset({"COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "OUT_OF_MEMORY", "DEADLINE"})


def _error(message, **extra):
    return {"ok": False, "error": message, **extra}


def stable_final(observed: dict) -> bool:
    """Vrai si l'observation decrit un etat que Slurm ne changera plus."""
    words = str(observed.get("state") or "").split()
    return bool(observed.get("finished")) and bool(words) and words[0].rstrip("+") in STABLE_FINAL_STATES


def reusable(previous: dict | None, max_age_seconds: int) -> bool:
    """Une observation enregistree peut-elle remplacer une lecture Slurm ?

    `max_age_seconds=0` exige toujours une lecture. Une observation en echec
    n'est jamais reutilisee. L'invalidation par une action sur le job (annulation,
    signal) est verifiee a part, dans le registre.
    """
    if not previous or max_age_seconds <= 0:
        return False
    result = previous.get("result")
    if not isinstance(result, dict) or result.get("ok") is not True:
        return False
    return stable_final(result) or float(previous.get("age_seconds", max_age_seconds + 1)) <= max_age_seconds


def status_command(jid):
    if not re.fullmatch(r"\d+(?:_(?:\d+|\[[\d,:%-]+\]))?", jid):
        raise ValueError("Identifiant Slurm invalide")
    quoted = shlex.quote(jid)
    # Un seul `squeue` ; la comptabilite n'est lue qu'apres la sortie de la file.
    return (
        "live=$(squeue -h -j {jid} -o '{fields}') || exit $?; "
        "printf '###LIVE\n%s\n' \"$live\"; "
        "if [ -z \"$live\" ]; then echo '###PAST'; sacct -j {jid} -X -n -P "
        "-o JobID,JobName,Partition,State,Elapsed,ExitCode,Start,End || exit $?; fi"
    ).format(jid=quoted, fields=LIVE_FORMAT)

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
        # `%S` du meme releve ; une section START reste lue pour les releves
        # produits par une version precedente du serveur.
        start = parts[9].strip() if len(parts) > 9 else (sections.get("START") or [""])[0]
        cpus = parts[10].strip() if len(parts) > 10 else ""
        memory = parts[11].strip() if len(parts) > 11 else ""
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
            "estimated_start": (start or None) if state == "PENDING" else None,
            "cpus": int(cpus) if cpus.isdigit() else None,
            "min_memory": memory if re.fullmatch(r"[0-9.]+[KMGTP]?[nc]?", memory) else None,
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
