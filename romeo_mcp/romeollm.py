"""Adaptateur borne de la CLI RomeoLLMTool, sans inference sur le login.

La CLI conserve la responsabilite des fiches, de Slurm et de la gateway.
Le MCP n'invente ni format JSON ni emplacement de l'installation distante.
"""
from __future__ import annotations

import hashlib
import json
import re
import shlex
import time
from urllib.parse import urlsplit

from .cluster import format_slurm_time, parse_duration, require_account
from .config import setting
from .execution_backend import _error, _sh
from .privacy import redact_text
from .registry import PLAN_TTL_SECONDS, registry
from .resource_locks import ResourceLease
from .ssh import SSHError, session

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9/_.:-]{0,255}\Z")
_JOB = re.compile(r"[1-9][0-9]{0,19}\Z")
_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_KEY_LINE = re.compile(r"^.*\b(?:api\s+key|gateway\s+key|internal\s+key|cl[eé](?:\s+api)?)\b.*$", re.I | re.M)
_MISSING = "ROMEOLLMTOOL_EXECUTABLE_UNAVAILABLE"
_KIND = "romeollm_launch"
SHARED_EXECUTABLE = "/apps/romeotools/romeollmtool/romeollmtool"


def _name(value: str, label: str = "fiche") -> str:
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        raise ValueError(f"{label} invalide : 1 a 128 lettres, chiffres, points, tirets ou underscores.")
    return value


def _integer(value: int, low: int, high: int, label: str) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{label} doit etre un entier entre {low} et {high}.")
    return value


def _job(value: str) -> str:
    if not isinstance(value, str) or not _JOB.fullmatch(value):
        raise ValueError("job_id doit etre un numero de job Slurm explicite, sans nom de fiche ni --all.")
    return value


def _executable() -> str:
    value = setting("ROMEO_LLM_EXECUTABLE", "romeollmtool")
    if (not value or len(value) > 1024 or value.startswith("-")
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError("ROMEO_LLM_EXECUTABLE doit designer un seul executable distant, sans caractere de controle.")
    return value


def _command(argv: list[str]) -> str:
    # Ne jamais evaluer une chaine de configuration comme un fragment shell.
    missing = f"printf '%s\\n' '{_MISSING}'; exit 127"
    fallback = missing
    if argv[0] == "romeollmtool":
        shared = shlex.quote(SHARED_EXECUTABLE)
        fallback = (f"if [ -f {shared} ] && [ -x {shared} ]; then "
                    f"NO_COLOR=1 TERM=dumb {shlex.join([SHARED_EXECUTABLE, *argv[1:]])}; "
                    f"else {missing}; fi")
    return (f"if command -v {shlex.quote(argv[0])} >/dev/null 2>&1; then\n"
            f"NO_COLOR=1 TERM=dumb {shlex.join(argv)}\n"
            f"else {fallback}; fi")


def _run(s, args: list[str], *, read_only: bool = True, timeout: int = 30,
         max_chars: int = 16000, executable: str | None = None) -> dict:
    argv = [executable or _executable(), *args]
    try:
        result = _sh(s, _command(argv), read_only=read_only, timeout=timeout, max_chars=max_chars)
    except SSHError:
        # Le transport peut citer la commande (et donc un message de chat).
        return _error("Connexion SSH interrompue ou delai depasse pendant RomeoLLMTool.",
                      execution_outcome="unknown" if not read_only else "unobserved",
                      retry_safe=read_only)
    output = _KEY_LINE.sub("[REDACTED]", redact_text(_ANSI.sub("", result.stdout)))
    common = {"output": output, "exit_code": result.rc, "truncated": result.truncated,
              "complete": not result.truncated, "observed_at": time.time()}
    if result.rc == 127 and _MISSING in result.stdout:
        return _error("Executable RomeoLLMTool introuvable dans cette session SSH.", **common,
                      available=False, execution_started=False, retry_safe=True,
                      next_step="Verifier l'acces au service sur ROMEO ; le PATH et l'installation partagee ont ete sondes. "
                                "ROMEO_LLM_EXECUTABLE accepte le chemin distant fourni par les administrateurs.")
    if not result.ok:
        return _error("La commande RomeoLLMTool a echoue ; consulter output.", **common,
                      execution_outcome="unknown" if not read_only else "failed", retry_safe=read_only)
    return {"ok": True, **common, "output_sha256": hashlib.sha256(result.stdout.encode()).hexdigest()}


def catalog(fiche: str | None, category: str | None) -> dict:
    if fiche is not None and category is not None:
        raise ValueError("Choisir fiche pour son detail, ou category pour filtrer la liste.")
    args = ["catalog", "show", _name(fiche)] if fiche is not None else ["catalog", "list"]
    if category is not None:
        args += ["--category", _name(category, "category")]
    return _run(session(), args)


def inspect(action: str) -> dict:
    if action not in {"status", "engines", "doctor"}:
        raise ValueError("Inspection RomeoLLMTool inconnue.")
    return _run(session(), [action])


def stats(days: int) -> dict:
    _integer(days, 1, 365, "days")
    return _run(session(), ["stats", "--days", str(days)])


def logs(job_id: str, lines: int) -> dict:
    _job(job_id)
    _integer(lines, 1, 500, "lines")
    return _run(session(), ["logs", job_id, "-n", str(lines)])


def _connection(result: dict, s, local_port: int) -> dict:
    result["api_key_exposed"] = False
    result["api_key_command"] = _command([_executable(), "gateway", "show-key"])
    result["api_key_scope"] = "gateway_only"
    if not result["ok"] or not result.get("complete"):
        return result
    connections = []
    for raw in dict.fromkeys(re.findall(r"https?://[^\s<>\x1b]+", result["output"])):
        url = raw.rstrip(".,;)'\"|")
        try:
            parsed = urlsplit(url)
            host, port = parsed.hostname, parsed.port
        except ValueError:
            continue
        if (not host or not port or parsed.username or parsed.password or parsed.query or parsed.fragment
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,252}", host)):
            continue
        connections.append({"remote_url": url,
            "local_url": f"{parsed.scheme}://localhost:{local_port}{parsed.path}",
            "ssh_tunnel_command": shlex.join(["ssh", "-N", "-L", f"{local_port}:{host}:{port}", s.host]),
            "tunnel_opened": False, "authentication_verified": False})
    result["connections"] = connections
    return result


def endpoint(job_id: str, local_port: int) -> dict:
    _job(job_id)
    _integer(local_port, 1024, 65535, "local_port")
    s = session()
    return _connection(_run(s, ["endpoint", job_id]), s, local_port)


def gateway_status(local_port: int) -> dict:
    _integer(local_port, 1024, 65535, "local_port")
    s = session()
    result = _run(s, ["gateway", "status"])
    # La CLI officielle utilise rc=1 pour cet etat normal et explicite.
    if (result.get("exit_code") == 1 and result.get("complete") is True
            and result.get("output", "").strip() == "La gateway ne tourne pas (romeollmtool gateway start)."):
        result.pop("error", None)
        result.update(ok=True, state="stopped", ready=False, execution_outcome="observed")
    return _connection(result, s, local_port)


def _target(s) -> dict:
    return {"host": s.host, "user": s.user, "home": s.home}


def _lease(target: dict) -> ResourceLease:
    key = hashlib.sha256(json.dumps(target, sort_keys=True).encode()).hexdigest()
    return ResourceLease([("action:romeollm:" + key, True)])


def prepare_launch(fiche: str, project_code: str | None, time_limit: str,
                   reservation: str | None) -> dict:
    _name(fiche)
    account = require_account(project_code)
    seconds = parse_duration(time_limit)
    if not 60 <= seconds <= 86400:
        raise ValueError("RomeoLLMTool exige une duree entre 1 minute et 24 heures.")
    args = ["launch", fiche, "--project-code", account, "--time", format_slurm_time(seconds), "--no-wait"]
    if reservation is not None:
        args += ["--reservation", _name(reservation, "reservation")]
    s = session()
    executable = _executable()
    config = _run(s, ["catalog", "show", fiche], executable=executable)
    if not config["ok"] or not config["complete"]:
        return {**config, "ok": False, "error": "Fiche illisible ou incomplete ; aucun plan executable.", "submitted": False}
    dry_run = _run(s, [*args, "--dry-run"], executable=executable, max_chars=64000)
    if not dry_run["ok"] or not dry_run["complete"] or not dry_run["output"].strip():
        return {**dry_run, "ok": False, "error": "Apercu du lancement absent ou incomplet ; aucun plan executable.", "submitted": False}
    target = _target(s)
    preview = {"fiche": fiche, "project_code": account, "time_limit": format_slurm_time(seconds),
        "command": shlex.join([executable, *args]), "config_preview": config["output"],
        "script_preview": dry_run["output"], "warnings": [
            "Chaque nouveau plan lance un job distinct. Le meme plan ne peut etre execute qu'une fois.",
            "La CLI regenerera son script ; le MCP reverifie la fiche avant le lancement, sans figer les fichiers distants."]}
    saved = registry().prepare_submission({"kind": _KIND, "target": target, "entries": [],
        "args": args, "executable": executable, "catalog_sha256": config["output_sha256"], "preview": preview})
    return {"ok": True, "submitted": False, "mode": "prepared", **saved, **preview,
            "next_step": "Relire le plan, puis romeollm_launch(plan_id=..., confirm=true)."}


def launch(plan_id: str, confirm: bool) -> dict:
    if confirm is not True:
        return _error("Le lancement exige confirm=true apres lecture du plan.", submitted=False)
    if not isinstance(plan_id, str) or not re.fullmatch(r"[a-f0-9]{32}", plan_id):
        raise ValueError("plan_id RomeoLLMTool invalide.")
    store = registry()
    saved = store.prepared_submission(plan_id)
    if not saved or saved["payload"].get("kind") != _KIND:
        return _error("Plan introuvable ou incompatible avec RomeoLLMTool.", submitted=False)
    if saved["state"] != "ready":
        if saved["state"] == "submitted":
            return {**saved["result"], "already_executed": True}
        return _error("Ce plan a deja ete tente ; consulter romeollm_status avant toute nouvelle preparation.",
                      state=saved["state"], previous_result=saved["result"], retry_safe=False)
    if saved["created_at"] + PLAN_TTL_SECONDS <= time.time():
        return _error("Plan expire (24 h) ; preparer un nouveau lancement.", submitted=False)
    payload = saved["payload"]
    s = session()
    if _target(s) != payload["target"] or _executable() != payload["executable"]:
        return _error("La cible SSH ou l'executable a change ; preparer un nouveau lancement.", submitted=False)
    with _lease(payload["target"]):
        config = _run(s, ["catalog", "show", payload["preview"]["fiche"]], executable=payload["executable"])
        if not config["ok"] or not config["complete"]:
            return {**config, "ok": False, "error": "Impossible de reverifier la fiche avant lancement.", "submitted": False}
        if config["output_sha256"] != payload["catalog_sha256"]:
            return _error("La fiche a change depuis la preparation ; relire un nouveau plan.", submitted=False)
        if not store.claim_submission(plan_id):
            return _error("Plan deja reserve, tente ou expire ; consulter romeollm_status.", submitted=False)
        try:
            result = _run(s, payload["args"], executable=payload["executable"], read_only=False, timeout=45)
        except Exception:
            # Une interruption apres le claim ne doit jamais rendre le plan rejouable.
            result = _error("Lancement interrompu ; resultat distant inconnu.", execution_outcome="unknown")
        success = result["ok"] and result.get("complete", False)
        result.update(plan_id=plan_id, plan_sha256=saved["sha256"],
            command_succeeded=bool(success), ready=None, result_validated=False,
            retry_safe=False, next_step="Consulter romeollm_status, puis romeollm_logs et romeollm_endpoint avec le numero de job.")
        match = re.search(r"^Submitted batch job ([1-9][0-9]{0,19})\s*$", result.get("output", ""), re.M)
        result["submission_observed"] = bool(success and match)
        if success and match:
            result["job_id"] = match.group(1)
        if not success:
            result.update(ok=False, execution_outcome="unknown")
        store.update_submission(plan_id, "submitted" if success else "uncertain", result)
        return result


def _mutate(args: list[str], confirm: bool) -> dict:
    if confirm is not True:
        return _error("Cette action exige confirm=true.", execution_started=False)
    s = session()
    with _lease(_target(s)):
        result = _run(s, args, read_only=False)
    result.update(result_validated=False, next_step="Verifier l'etat avec romeollm_status ou romeollm_gateway_status.")
    return result


def stop(job_id: str, confirm: bool) -> dict:
    _job(job_id)
    return _mutate(["stop", job_id], confirm)


def gateway_start(port: int | None, hours: int, confirm: bool) -> dict:
    _integer(hours, 1, 24, "hours")
    args = ["gateway", "start", "--hours", str(hours)]
    if port is not None:
        _integer(port, 1024, 65535, "port")
        args += ["--port", str(port)]
    return _mutate(args, confirm)


def gateway_stop(confirm: bool) -> dict:
    # Le defaut de la CLI annule aussi tous les jobs ; ne jamais l'heriter.
    return _mutate(["gateway", "stop", "--keep-jobs"], confirm)


def chat(model: str, message: str, max_tokens: int, timeout_seconds: int) -> dict:
    if not isinstance(model, str) or not _MODEL.fullmatch(model):
        raise ValueError("model doit etre un nom de fiche ou un identifiant de modele simple.")
    if not isinstance(message, str) or not message.strip() or len(message) > 16000 or "\0" in message:
        raise ValueError("message doit contenir de 1 a 16000 caracteres, sans octet nul.")
    _integer(max_tokens, 1, 8192, "max_tokens")
    _integer(timeout_seconds, 5, 90, "timeout_seconds")
    return _run(session(), ["chat", model, "-m", message, "--no-stream", "--hide-think",
                            "--max-tokens", str(max_tokens)], read_only=False, timeout=timeout_seconds)
