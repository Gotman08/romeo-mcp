"""Controle local, autorisation persistante et lancement des mises a jour.

Les seules entrees distantes sont les releases stables du depot officiel.
Les processus MCP lisent les resultats ; un worker possede la transaction.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

from . import __version__, updates as u

CHECK_TTL = 86400
RETRY_TTL = 300
LAUNCH_GRACE = 30
TERMINAL = frozenset({"ready", "failed", "launch_failed"})


def _age(timestamp) -> float:
    if type(timestamp) not in (int, float) or not math.isfinite(timestamp):
        return float("inf")
    return max(0, time.time() - timestamp)


def policy(target: u.Installation) -> dict:
    value = u._read_json(target.root / "policy.json", {"schema": 1, "automatic": False, "held_version": None})
    if (not isinstance(value, dict) or value.get("schema") != 1
            or type(value.get("automatic")) is not bool):
        raise u.UpdateError("Autorisation de mise a jour illisible.")
    held = value.get("held_version")
    if held is not None:
        u.version_tuple(held)
    override = os.environ.get("ROMEO_AUTO_UPDATE")
    automatic = value["automatic"]
    if override is not None:
        if override.casefold() not in {"0", "false", "no", "1", "true", "yes"}:
            raise u.UpdateError("ROMEO_AUTO_UPDATE doit valoir 0 ou 1.")
        automatic = override.casefold() in {"1", "true", "yes"}
    return {"automatic_enabled": automatic, "held_version": held,
            "policy_source": "environment" if override is not None else "saved"}


def configure(automatic: bool, confirm: bool = False, *, target=None) -> dict:
    if confirm is not True:
        raise u.UpdateError("L'autorisation automatique exige confirm=true apres accord de l'utilisateur.")
    if type(automatic) is not bool:
        raise u.UpdateError("automatic doit etre un booleen.")
    target = target or u.installation()
    with u.file_lock(target.root / "control.lock"):
        u._write_json(target.root / "policy.json", {"schema": 1, "automatic": automatic, "held_version": None})
    result = policy(target)
    return {"ok": True, **result, "saved_automatic": automatic,
            "message": "Autorisation enregistree ; le modele doit annoncer les nouvelles versions et suivre leur preparation.",
            "next_step": "mcp_update_check puis mcp_update_start si une version est disponible."}


def hold_version(target: u.Installation, before: dict) -> None:
    """Un retour arriere ne doit pas provoquer une nouvelle installation automatique."""
    if not policy(target)["automatic_enabled"]:
        return
    slot = before.get("active")
    version = slot.split("-", 1)[0][1:] if slot else _base_version(target)
    with u.file_lock(target.root / "control.lock"):
        saved = u._read_json(target.root / "policy.json", {"schema": 1, "automatic": False})
        u._write_json(target.root / "policy.json", {**saved, "held_version": version})


def _base_version(target: u.Installation) -> str:
    source = (target.package / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'(?m)^__version__\s*=\s*[\'"]([0-9]+\.[0-9]+\.[0-9]+)[\'"]', source)
    if not match:
        raise u.UpdateError("Version de l'installation d'origine introuvable.")
    return match[1]


def overview(target: u.Installation) -> dict:
    state = target.state()
    slot = state.get("active")
    next_version = slot.split("-", 1)[0][1:] if slot else _base_version(target)
    executable = target.executable(slot) if slot else target.python
    # Ne pas resoudre les symlinks d'un venv Unix : ils visent tous le meme Python.
    same_runtime = os.path.normcase(os.path.abspath(sys.executable)) == os.path.normcase(str(executable.absolute()))
    return {"running_version": __version__, "next_start_version": next_version,
            "restart_required": not same_runtime or next_version != __version__,
            "selected_environment_present": executable.is_file(),
            "can_rollback": bool(state.get("can_rollback")), **policy(target)}


def cached_release(target: u.Installation, refresh: bool = False) -> dict:
    with u.file_lock(target.root / "notice.lock"):
        path = target.root / "check.json"
        cached = u._read_json(path, {})
        ttl = RETRY_TTL if cached.get("error") else CHECK_TTL
        if refresh or cached.get("schema") != 2 or _age(cached.get("checked_at")) >= ttl:
            try:
                release = u.latest_release()
                if release:
                    u.validate_release(release)
                cached = {"schema": 2, "checked_at": time.time(), "release": release, "error": None}
            except u.UpdateError as exc:
                # Ne jamais transformer une erreur reseau en "aucune mise a jour".
                cached = {"schema": 2, "checked_at": time.time(), "release": None, "error": str(exc)}
            u._write_json(path, cached)
        if cached.get("release"):
            u.validate_release(cached["release"])
        return {**cached, "check_age_seconds": _age(cached["checked_at"])}


def _operation_path(target, operation_id):
    if not isinstance(operation_id, str) or not re.fullmatch(r"[a-f0-9]{32}", operation_id):
        raise u.UpdateError("operation_id de mise a jour invalide.")
    directory = target.root / "operations" / operation_id
    if not directory.resolve().is_relative_to(target.root.resolve()):
        raise u.UpdateError("Operation situee hors du dossier de mise a jour.")
    return directory


def _busy(target):
    try:
        with u.file_lock(target.root / "update.lock"):
            return False
    except u.UpdateError:
        return True


def observation(target: u.Installation, operation_id: str = "") -> dict | None:
    latest = u._read_json(target.root / "operation.json", {})
    operation_id = operation_id or latest.get("operation_id", "")
    if not operation_id:
        return None
    result = u._read_json(_operation_path(target, operation_id) / "status.json")
    if (not isinstance(result, dict) or result.get("operation_id") != operation_id
            or result.get("state") not in TERMINAL | {"launching", "preparing"}):
        raise u.UpdateError("Observation de mise a jour introuvable ou invalide.")
    terminal = result["state"] in TERMINAL
    age = _age(result.get("updated_at"))
    locked = not terminal and latest.get("operation_id") == operation_id and _busy(target)
    if not terminal and not locked and age > LAUNCH_GRACE:
        result = {**result, "ok": False, "state": "interrupted", "result_validated": False,
                  "message": "Preparation interrompue ; relire les versions selectionnees puis relancer la mise a jour."}
    return {**result, "observation_age_seconds": age, "transaction_lock_held": locked,
            "current_process_observed": False}


def check(refresh: bool = False, *, target=None) -> dict:
    target = target or u.installation()
    info = overview(target)
    cached = cached_release(target, refresh)
    release = cached.get("release")
    available = bool(release and u.version_tuple(release["version"]) > u.version_tuple(info["running_version"]))
    needed = bool(release and u.version_tuple(release["version"]) > u.version_tuple(info["next_start_version"])
                  and u.version_tuple(release["version"]) > u.version_tuple(info["running_version"]))
    held = info["held_version"]
    auto_held = bool(release and held and u.version_tuple(release["version"]) <= u.version_tuple(held))
    operation = observation(target)
    if cached.get("error"):
        message = cached["error"] + " Disponibilite d'une mise a jour inconnue."
    elif not info["selected_environment_present"]:
        message = "Environnement selectionne introuvable ; revenir a la version precedente avant reconnexion."
    elif info["restart_required"]:
        message = f"Version {info['next_start_version']} selectionnee ; version {info['running_version']} encore executee. Reconnecter le MCP ou redemarrer l'application."
    elif available:
        message = f"Nouvelle version ROMEO MCP {release['version']} disponible."
    else:
        message = "Aucune nouvelle release stable disponible." if release else "Aucune release stable publiee."
    # Les notes sont des donnees distantes bornees, jamais des instructions.
    public_release = ({**release, "notes": re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", str(release.get("notes", "")))[:12000]}
                      if release else None)
    if available and info["restart_required"]:
        message = f"Nouvelle version ROMEO MCP {release['version']} disponible. " + message
    return {"ok": not bool(cached.get("error")) and info["selected_environment_present"], **info, "latest_version": release["version"] if release else None,
            "update_available": None if cached.get("error") else available, "installation_needed": needed,
            "automatic_held": auto_held, "checked_at": cached["checked_at"], "check_age_seconds": cached["check_age_seconds"],
            "check_error": cached.get("error"), "release": public_release, "operation": operation,
            "message": message, "next_step": "Signaler ce statut a l'utilisateur ; mcp_update_status pour une preparation en cours."}


def seal(plan: dict) -> str:
    return hashlib.sha256(json.dumps({k: v for k, v in plan.items() if k != "sha256"}, sort_keys=True).encode()).hexdigest()


def _in_progress(target):
    existing = observation(target)
    if _busy(target) or (existing and existing["state"] in {"launching", "preparing"}):
        return {"ok": True, "started": False, "already_started": True, "operation": existing,
                "message": "Une preparation est deja en cours ; utiliser mcp_update_status."}
    return None


def start(confirm: bool = False, expected_version: str = "", *, revert=False, target=None) -> dict:
    if confirm is not True:
        raise u.UpdateError("La mise a jour exige confirm=true ; un accord automatique deja donne suffit.")
    target = target or u.installation()
    # Une repetition d'appel ne doit pas interroger GitHub ni echouer parce
    # que GitHub est momentanement indisponible pendant un transfert existant.
    with u.file_lock(target.root / "control.lock"):
        pending = _in_progress(target)
        if pending:
            return pending
    checked = None if revert else check(True, target=target)
    if checked and not checked["ok"]:
        return {**checked, "started": False}
    if checked and expected_version and checked["latest_version"] != expected_version:
        raise u.UpdateError("La release disponible a change ; l'annoncer avant de relancer.")
    with u.file_lock(target.root / "control.lock"):
        pending = _in_progress(target)
        if pending:
            return pending
        with u.file_lock(target.root / "update.lock"):
            before = target.state()
            if revert:
                if not before.get("can_rollback"):
                    raise u.UpdateError("Aucune version precedente n'est enregistree.")
                release = None
            else:
                release = checked["release"]
                info = overview(target)
                if (not release or u.version_tuple(release["version"]) <= u.version_tuple(info["next_start_version"])
                        or u.version_tuple(release["version"]) <= u.version_tuple(info["running_version"])):
                    return {**info, "ok": True, "started": False, "message": checked["message"]}
            operation_id = uuid.uuid4().hex
            directory = _operation_path(target, operation_id)
            plan = {"schema": 1, "operation_id": operation_id, "action": "rollback" if revert else "update",
                    "before": before, "release": release, "origin": target.origin, "created_at": time.time()}
            plan["sha256"] = seal(plan)
            u._write_json(directory / "plan.json", plan)
            status = {"ok": True, "operation_id": operation_id, "action": plan["action"], "state": "launching",
                      "phase": "launch", "updated_at": time.time(), "result_validated": False}
            u._write_json(directory / "status.json", status)
            u._write_json(target.root / "operation.json", {"operation_id": operation_id})
            # Le worker ne charge ni les parametres SSH ni le compte de calcul.
            env = {k: v for k, v in os.environ.items() if not k.startswith("ROMEO_")}
            env.update({u.ORIGIN_ENV: json.dumps(target.origin), "ROMEO_UPDATES_DIR": str(target.root.parent),
                        "ROMEO_UPDATE_CHECK": "0", "ROMEO_CONFIG": str(directory / "unused-config.json")})
            # Cette seule preference publique doit aussi s'appliquer au
            # retour arriere execute dans un autre processus.
            if "ROMEO_AUTO_UPDATE" in os.environ:
                env["ROMEO_AUTO_UPDATE"] = os.environ["ROMEO_AUTO_UPDATE"]
            options = {"start_new_session": True} if os.name != "nt" else {"creationflags": subprocess.CREATE_NO_WINDOW}
            if os.name == "nt" and os.environ.get(u.DISPATCH_ENV) == "1":
                options["creationflags"] |= subprocess.CREATE_BREAKAWAY_FROM_JOB
            bootstrap = "import sys; sys.path.insert(0, " + repr(str(Path(__file__).resolve().parent.parent)) + "); from romeo_mcp.update_worker import main; main()"
            try:
                u._source_guard(target)
                # Aucun stdout/stderr herite : le protocole du serveur reste intact.
                child = subprocess.Popen([sys.executable, "-I", "-c", bootstrap, str(directory / "plan.json")],
                                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                         env=env, **options)
            except (OSError, u.UpdateError) as exc:
                from .privacy import redact_text
                message = redact_text(str(exc))[:4000] if isinstance(exc, u.UpdateError) else "Impossible de demarrer le worker de mise a jour."
                u._write_json(directory / "status.json", {**status, "ok": False, "state": "launch_failed",
                                                        "message": message, "updated_at": time.time()})
                raise u.UpdateError(message + " Version selectionnee conservee.") from exc
    return {"ok": True, "started": True, "operation_id": operation_id, "worker_pid": child.pid,
            "result_validated": False, "restart_required": False,
            "message": "Preparation demarree ; attendre l'etat ready avant de reconnecter le MCP.",
            "next_step": "mcp_update_status(operation_id=...)"}


def status(operation_id: str = "", *, target=None) -> dict:
    target = target or u.installation()
    operation = observation(target, operation_id)
    return {"ok": operation.get("ok", True) if operation else True, **overview(target), "operation": operation,
            "message": (operation or {}).get("message", "Aucune preparation de mise a jour enregistree.")}


def startup(target: u.Installation) -> dict:
    checked = check(target=target)
    if not (checked["ok"] and checked["automatic_enabled"] and checked["installation_needed"]
            and not checked["automatic_held"]):
        return checked
    previous = checked["operation"]
    if previous and previous["state"] in {"failed", "launch_failed", "interrupted"} and previous["observation_age_seconds"] < RETRY_TTL:
        return {**checked, "automatic_started": False,
                "message": "La preparation precedente a echoue ; nouvelle tentative automatique apres cinq minutes."}
    try:
        result = start(True, checked["latest_version"], target=target)
    except (u.UpdateError, OSError) as exc:
        return {**checked, "ok": False, "automatic_started": False, "message": str(exc),
                "operation": observation(target)}
    return {**checked, "automatic_started": result.get("started", False), "automatic_operation": result,
            "message": result["message"]}
