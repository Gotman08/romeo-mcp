"""Small combined filters compiled exclusively from whitelisted SQL fragments."""
from __future__ import annotations

from datetime import datetime, timezone
import re
import shlex

FIELDS = {"etat": "state", "state": "state", "validation": "validation", "partition": "partition",
          "depuis": "since", "since": "since", "avant": "before", "before": "before", "cpu": "cpu", "gpu": "gpu"}


def compile_query(query, normalize):
    try:
        tokens = shlex.split(query)
    except ValueError:  # A quote still being typed is text, not a fatal reader error.
        tokens = query.split()
    clauses, values, text = [], [], []
    for token in tokens:
        field, separator, argument = token.partition(":")
        field = FIELDS.get(normalize(field)) if separator else None
        if not field or not argument:
            text.append(token)
            continue
        if field == "state":
            clauses.append("(state_key=? OR lower(state)=?)")
            values.extend((normalize(argument.replace("_", " ")), argument.lower()))
        elif field == "validation":
            option = normalize(argument).replace("_", " ")
            choice = {"verified": "verified", "verifie": "verified", "check": "check", "a verifier": "check",
                      "pending": "pending", "a venir": "pending", "absent": "absent", "non valide": "absent"}.get(option)
            if choice is None:
                raise ValueError("validation : verified/check/pending/absent")
            clauses.append({"verified": "json_extract(record,'$.result_validated')=1", "check": "unverified=1",
                            "pending": "active=1 AND unverified=0", "absent": "active=0 AND unverified=0 AND json_extract(record,'$.result_validated')=0"}[choice])
        elif field == "partition":
            clauses.append("lower(json_extract(record,'$.partition'))=?")
            values.append(argument.lower())
        elif field in {"since", "before"}:
            try:
                instant = datetime.strptime(argument, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
            except ValueError as exc:
                raise ValueError("Date de filtre : YYYY-MM-DD en UTC") from exc
            clauses.append("date" + (">=?" if field == "since" else "<?"))
            values.append(instant)
        else:
            if field == "gpu" and normalize(argument) in {"yes", "oui", "no", "non"}:
                operator, amount = (">", 0) if normalize(argument) in {"yes", "oui"} else ("=", 0)
            else:
                match = re.fullmatch(r"(>=|<=|>|<|=)?([0-9]{1,9})", argument)
                if not match:
                    raise ValueError("Filtre CPU/GPU : nombre, >=nombre, oui/non pour GPU")
                operator, amount = match.group(1) or "=", int(match.group(2))
            expression = ("coalesce(json_extract(record,'$.resources.observed.gpus'),json_extract(record,'$.resources.requested.gpus'),"
                          "json_extract(record,'$.resources.requested.gpus_per_node'),json_extract(record,'$.resources.requested.gpus_per_task'))") if field == "gpu" else (
                          "json_extract(record,'$.resources.requested.cpus_per_task')")
            clauses.append(expression + operator + "?")
            values.append(amount)
    return " AND ".join(clauses) or "1", tuple(values), " ".join(text)
