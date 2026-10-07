"""Rapports de defauts MCP, locaux ou publies avec autorisation persistante."""
from __future__ import annotations

import importlib.metadata
import os
import platform
import re
import sys
import time

from . import __version__
from .issue_github import GitHubClient, GitHubError, authentication, marker
from .issue_privacy import private_values, public_text
from .issue_store import MAX_PER_DAY, MIN_INTERVAL, PublicationDelay, ReportStore
from .updates import REPOSITORY

CATEGORIES = ("bug", "performance", "maintainability", "documentation")
_TOOL = re.compile(r"[a-z][a-z0-9_]{0,63}")
_ERROR_MESSAGES = {
    "github_authentication_missing": "Configurer gh auth login ou ROMEO_GITHUB_TOKEN ; le rapport reste local.",
    "github_credentials_invalid": "Identifiant GitHub invalide ; le rapport reste local.",
    "github_http_401": "Authentification GitHub refusee ; verifier la connexion sans joindre ses identifiants.",
    "github_http_403": "GitHub refuse l'action ou limite les requetes ; verifier les droits Issues et attendre retry_after.",
    "github_http_404": "Depot ou issue inaccessible avec cette connexion GitHub.",
    "github_http_410": "Les issues de ce depot sont desactivees.",
    "github_http_422": "GitHub refuse ce rapport ou limite les creations ; conserver le rapport local.",
    "github_http_429": "Limite GitHub atteinte ; attendre retry_after.",
    "github_lookup_limit": "Historique GitHub trop volumineux ou trop lent pour exclure un doublon ; aucun envoi.",
}


def policy_get(*, store: ReportStore | None = None) -> dict:
    store = store or ReportStore()
    saved = store.policy()
    override = os.environ.get("ROMEO_AUTO_ISSUES")
    enabled = saved["saved_automatic"]
    if override is not None:
        if override.lower() not in ("0", "1", "false", "true", "off", "on"):
            raise ValueError("ROMEO_AUTO_ISSUES doit valoir 0 ou 1.")
        enabled = override.lower() in ("1", "true", "on")
    return {"ok": True, "repository": REPOSITORY, "automatic_enabled": enabled,
            "policy_source": "environment" if override is not None else "saved", **saved,
            "authentication": authentication(), "max_new_issues_per_24h": MAX_PER_DAY,
            "min_seconds_between_creations": MIN_INTERVAL, "background_collection": False}


def policy_set(automatic: bool, confirm: bool = False, *, store: ReportStore | None = None) -> dict:
    if type(automatic) is not bool or type(confirm) is not bool:
        raise ValueError("automatic et confirm doivent etre des booleens.")
    if automatic and not confirm:
        raise ValueError("confirm=true exige l'accord initial de l'utilisateur pour publier automatiquement des rapports publics.")
    store = store or ReportStore()
    # Verifier aussi l'override avant d'enregistrer un accord.
    policy_get(store=store)
    store.configure(automatic)
    return policy_get(store=store)


def _version(distribution: str) -> str:
    try:
        value = importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return "unknown"
    return value if re.fullmatch(r"[A-Za-z0-9.+-]{1,48}", value) else "unknown"


def document(tool_name: str, summary: str, observed: str, expected: str, steps: list[str] | None = None,
             category: str = "bug", error_code: str = "") -> dict:
    if not isinstance(tool_name, str) or not _TOOL.fullmatch(tool_name) or tool_name.startswith("mcp_issue_"):
        raise ValueError("Nom d'outil MCP attendu ; ne pas auto-signaler les outils de rapport eux-memes.")
    if category not in CATEGORIES:
        raise ValueError("Categorie attendue : bug, performance, maintainability ou documentation.")
    if steps is None:
        steps = []
    if not isinstance(steps, list) or len(steps) > 8:
        raise ValueError("Fournir au maximum huit etapes de reproduction minimales.")
    if error_code and (not isinstance(error_code, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", error_code)):
        raise ValueError("error_code doit etre un code technique court, sans texte libre.")
    secrets = private_values()
    redacted = False

    def clean(value, maximum):
        nonlocal redacted
        result, changed = public_text(value, maximum, secrets=secrets)
        redacted = redacted or changed
        return result

    content = {"schema": 1, "repository": REPOSITORY, "tool_name": tool_name, "category": category,
               "summary": " ".join(clean(summary, 160).split())[:160], "observed": clean(observed, 3000),
               "expected": clean(expected, 2000), "steps": [clean(step, 500) for step in steps],
               "error_code": clean(error_code, 64) if error_code else ""}
    system = platform.system()
    machine = platform.machine().lower()
    content["context"] = {"romeo_version": __version__, "python_version": sys.version.split()[0],
                          "mcp_version": _version("mcp"),
                          "os": system if system in ("Windows", "Linux", "Darwin") else "unknown",
                          "architecture": machine if machine in ("amd64", "x86_64", "arm64", "aarch64") else "unknown"}
    content["redaction_applied"] = redacted
    return content


def _literal(text: str) -> str:
    # Toute description est du texte cite, pas une commande ni un lien actif.
    return "\n".join("    " + line for line in text.splitlines())


def render(record: dict) -> tuple[str, str]:
    doc = record["report"]
    title = f"[ROMEO MCP/{doc['category']}] {doc['tool_name']}: {doc['summary']}"
    context = "\n".join(f"- {key}: `{value}`" for key, value in doc["context"].items())
    steps = "\n".join(f"{index}. {step}" for index, step in enumerate(doc["steps"], 1)) or "Non fournies."
    body = ("Rapport genere par un assistant via ROMEO MCP. Le diagnostic doit etre verifie par un mainteneur.\n\n"
            f"## Outil\n\n`{doc['tool_name']}` — `{doc['category']}`\n\n"
            f"## Probleme observe\n\n{_literal(doc['observed'])}\n\n"
            f"## Comportement attendu\n\n{_literal(doc['expected'])}\n\n"
            f"## Reproduction minimale\n\n{_literal(steps)}\n\n"
            f"## Code d'erreur\n\n{_literal(doc['error_code'] or 'Non fourni.')}\n\n"
            f"## Versions du client\n\n{context}\n\n"
            "Les arguments d'outils, scripts, journaux, fichiers, identifiants SSH et donnees scientifiques ne sont pas collectes.\n\n"
            + marker(record["fingerprint"]))
    return title, body


def _result(record: dict, *, created: bool = False, message: str = "") -> dict:
    return {"ok": record["state"] not in ("failed", "publication_unknown", "rate_limited"),
            "report_id": record["report_id"], "repository": REPOSITORY, "created": created,
            "published": record["result_validated"], "result_validated": record["result_validated"],
            "issue_url": record["issue_url"], "retry_after": record["retry_after"], "status": record, "message": message}


def report(tool_name: str, summary: str, observed: str, expected: str, steps: list[str] | None = None,
           category: str = "bug", error_code: str = "", *, store: ReportStore | None = None) -> dict:
    store = store or ReportStore()
    policy = policy_get(store=store)
    record = store.save(document(tool_name, summary, observed, expected, steps, category, error_code))
    if policy["automatic_enabled"]:
        return publish(record["report_id"], store=store)
    return _result(record, message="Rapport filtre conserve localement. Publication automatique desactivee.")


def publish(report_id: str, confirm: bool = False, *, store: ReportStore | None = None,
            client: GitHubClient | None = None) -> dict:
    if type(confirm) is not bool:
        raise ValueError("confirm doit etre un booleen.")
    store = store or ReportStore()
    record = store.get(report_id)
    if record["result_validated"]:
        return _result(record, message="Issue deja observee ; aucun nouvel envoi.")
    if not policy_get(store=store)["automatic_enabled"] and not confirm:
        raise ValueError("Publication publique : confirm=true apres accord ponctuel, ou autorisation automatique preexistante.")
    with store.publication_lock():
        record = store.get(report_id)
        if record["result_validated"]:
            return _result(record, message="Issue deja observee ; aucun nouvel envoi.")
        policy = policy_get(store=store)
        if not policy["automatic_enabled"] and not confirm:
            raise ValueError("Autorisation automatique retiree avant publication.")
        retry_after = max(record["retry_after"], policy["retry_after"])
        if time.time() < retry_after:
            state = record["state"] if record["state"] in ("publishing", "publication_unknown") else "rate_limited"
            record = store.update(report_id, state, issue_number=record["issue_number"], issue_url=record["issue_url"],
                                  last_error=record["last_error"] or "publication_delayed", retry_after=retry_after)
            return _result(record, message="Attendre retry_after ; aucune requete GitHub lancee.")
        was_uncertain = record["state"] in ("publication_unknown", "publishing")
        creation_observed = False
        try:
            client = client or GitHubClient()
            digest = record["fingerprint"]
            existing = client.get(record["issue_number"], digest) if record["issue_number"] else client.find(digest)
            if existing:
                if record["issue_number"]:
                    title, body = render(record)
                    if existing["title"] != title or existing["body"].replace("\r\n", "\n").strip() != body.strip():
                        raise GitHubError("github_creation_unconfirmed", uncertain=True)
                state = "published" if record["issue_number"] else "duplicate"
                record = store.update(report_id, state, issue_number=existing["number"], issue_url=existing["url"])
                return _result(record, message="Issue observee sur GitHub ; aucun doublon cree.")
            if was_uncertain:
                record = store.update(report_id, "publication_unknown", last_error="github_creation_unconfirmed")
                return _result(record, message="Envoi precedent incertain et issue non retrouvee. Verifier GitHub manuellement ; aucun nouvel envoi automatique.")
            title, body = render(record)
            if not confirm and not policy_get(store=store)["automatic_enabled"]:
                return _result(record, message="Autorisation automatique retiree ; aucun envoi effectue.")
            store.start_attempt(report_id)
            issue = client.create(title, body, digest)
            creation_observed = True
            store.update(report_id, "publishing", issue_number=issue["number"], issue_url=issue["url"])
            observed = client.get(issue["number"], digest)
            if observed["title"] != title or observed["body"].replace("\r\n", "\n").strip() != body.strip():
                raise GitHubError("github_creation_unconfirmed", uncertain=True)
            record = store.update(report_id, "published", issue_number=observed["number"], issue_url=observed["url"])
            return _result(record, created=True, message="Issue creee puis relue sur GitHub ; publication verifiee.")
        except PublicationDelay as exc:
            record = store.update(report_id, "rate_limited", last_error="local_rate_limit", retry_after=exc.retry_after)
            return _result(record, message=str(exc))
        except GitHubError as exc:
            current = store.get(report_id)
            uncertain = was_uncertain or creation_observed or exc.uncertain
            retry_after = time.time() + exc.retry_seconds
            if exc.code in ("github_http_403", "github_http_429"):
                store.throttle(retry_after)
            record = store.update(report_id, "publication_unknown" if uncertain else "failed",
                                  issue_number=current["issue_number"], issue_url=current["issue_url"],
                                  last_error=exc.code, retry_after=retry_after)
            message = _ERROR_MESSAGES.get(exc.code, "GitHub indisponible ou reponse non verifiable ; le rapport reste local.")
            if uncertain:
                message += " Creation incertaine : ne pas annoncer de succes et ne pas renvoyer automatiquement."
            return _result(record, message=message)


def status(report_id: str = "", *, store: ReportStore | None = None) -> dict:
    store = store or ReportStore()
    if report_id:
        return _result(store.get(report_id))
    return {"ok": True, "repository": REPOSITORY, "reports": store.recent(), "network_checked": False}
