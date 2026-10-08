"""Explicit, read-only remote actions in a disposable UI-owned process."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time


def perform(action, identifier, *, demo=False, db=None):
    from .terminal_workspace import JOB_ID
    from .terminal_data import IDENTIFIER
    if action not in {"status", "efficiency", "logs", "resume", "service"}:
        raise ValueError("Action distante inconnue")
    if not (IDENTIFIER.fullmatch(identifier) if action == "service" else JOB_ID.fullmatch(identifier)):
        raise ValueError("Identifiant distant invalide")
    if demo:
        return {"ok": True, "action": action, "source": "source-demo", "observed_at": time.time(),
                "message": "Observation distante simulée ; aucune connexion."}
    if db is not None:
        os.environ["ROMEO_MCP_DB"] = str(db)
    # A UI failure must not implicitly publish a GitHub issue.
    os.environ["ROMEO_AUTO_ISSUES"] = "0"
    if action == "service":
        from .services import service_status
        result = service_status(identifier)
    elif action == "resume":
        from .checkpoint_operations import runtime_status
        result = runtime_status(identifier)
    else:
        from .outils_calcul import job_status, job_efficiency, job_log_tail
        result = {"status": job_status, "efficiency": job_efficiency,
                  "logs": lambda item: job_log_tail(item, lines=60, max_chars=8000, max_files=3)}[action](identifier)
    from .ssh import session
    from .cluster import DEFAULT_ACCOUNT
    connection = session()
    target = json.dumps({"host": connection.host, "user": connection.user, "account": DEFAULT_ACCOUNT}, sort_keys=True)
    return {"ok": result.get("ok") is True, "action": action,
            "source": "source-" + hashlib.sha256(target.encode()).hexdigest()[:8], "observed_at": time.time(),
            "message": "Observation distante enregistrée." if result.get("ok") is True else
                       "Observation distante indisponible ; les dernières preuves restent conservées."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", required=True, choices=("status", "efficiency", "logs", "resume", "service"))
    parser.add_argument("--identifier", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--db")
    args = parser.parse_args()
    try:
        result = perform(args.action, args.identifier, demo=args.demo, db=args.db)
    except Exception:
        result = {"ok": False, "message": "Observation distante impossible ; dernières preuves conservées."}
    print(json.dumps(result, ensure_ascii=True, allow_nan=False))


if __name__ == "__main__":
    main()
