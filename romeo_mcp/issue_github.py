"""Acces GitHub borne au seul depot ROMEO ; jamais de shell ni de token exporte."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .updates import REPOSITORY

API_ROOT = "https://api.github.com"
ENDPOINT = f"/repos/{REPOSITORY}/issues"
API_VERSION = "2026-03-10"
MAX_RESPONSE = 2 * 1024 * 1024
MAX_PAGES = 10
REQUEST_TIMEOUT = 10
LOOKUP_TIMEOUT = 30


class GitHubError(ValueError):
    def __init__(self, code: str, *, uncertain: bool = False, retry_seconds: int = 300):
        super().__init__(code)
        self.code = code
        self.uncertain = uncertain
        self.retry_seconds = max(60, min(10**12, retry_seconds))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Un token ne doit jamais suivre le deplacement d'un depot ou une URL
        # retournee par le serveur. Toutes les destinations sont construites ici.
        return None


def gh_executable() -> str | None:
    executable = shutil.which("gh")
    if executable:
        return executable
    if os.name == "nt":
        candidate = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "GitHub CLI/gh.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def authentication() -> dict:
    mode = os.environ.get("ROMEO_ISSUE_ACCOUNT", "auto")
    if mode not in ("auto", "personal", "bot"):
        raise ValueError("ROMEO_ISSUE_ACCOUNT doit valoir auto, personal ou bot.")
    if mode == "bot":
        return {"method": "bot_environment", "configured": bool(os.environ.get("ROMEO_GITHUB_BOT_TOKEN", "").strip()), "verified": False}
    if os.environ.get("ROMEO_GITHUB_TOKEN", "").strip():
        return {"method": "environment", "configured": True, "verified": False}
    if mode == "auto" and os.environ.get("ROMEO_GITHUB_BOT_TOKEN", "").strip():
        return {"method": "bot_environment", "configured": True, "verified": False}
    executable = gh_executable()
    return {"method": "gh" if executable else None, "configured": bool(executable), "verified": False}


def _json(raw: bytes | str, *, uncertain: bool) -> object:
    if len(raw) > MAX_RESPONSE:
        raise GitHubError("github_response_too_large", uncertain=uncertain)
    try:
        return json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise GitHubError("github_response_invalid", uncertain=uncertain) from exc


class GitHubClient:
    def __init__(self):
        method = authentication()["method"]
        self._token = os.environ.get("ROMEO_GITHUB_BOT_TOKEN" if method == "bot_environment" else "ROMEO_GITHUB_TOKEN", "").strip()
        if method == "bot_environment" and not self._token:
            raise GitHubError("github_authentication_missing")
        if not self._token:
            executable = gh_executable()
            if not executable:
                raise GitHubError("github_authentication_missing")
            self._token = self._gh_token(executable)
        if len(self._token) > 512 or not self._token.isascii() or re.search(r"\s", self._token):
            raise GitHubError("github_credentials_invalid")

    @staticmethod
    def _gh_token(executable: str) -> str:
        # Reutiliser le credential en memoire, puis utiliser le MEME transport
        # sans redirection. `gh api` peut suivre un depot deplace : on ne lui
        # delegue donc aucune publication. Aucun token ne passe en argument.
        env = {k: v for k, v in os.environ.items() if k in {
            "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE",
            "APPDATA", "LOCALAPPDATA", "LANG", "LC_ALL", "GH_CONFIG_DIR", "XDG_CONFIG_HOME",
            "GH_TOKEN", "GITHUB_TOKEN", "SSL_CERT_FILE", "SSL_CERT_DIR", "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY",
            "DBUS_SESSION_BUS_ADDRESS", "XDG_RUNTIME_DIR",
        }}
        env.update(GH_PROMPT_DISABLED="1", GH_NO_UPDATE_NOTIFIER="1", NO_COLOR="1")
        try:
            options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
            result = subprocess.run([executable, "auth", "token", "--hostname", "github.com"], stdin=subprocess.DEVNULL,
                                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                                    timeout=REQUEST_TIMEOUT, env=env, **options)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GitHubError("github_authentication_missing") from exc
        if result.returncode or not result.stdout.strip():
            raise GitHubError("github_authentication_missing")
        return result.stdout.strip()

    def request(self, method: str, endpoint: str, payload=None, *, timeout: float = REQUEST_TIMEOUT):
        if not (endpoint == ENDPOINT or endpoint.startswith(ENDPOINT + "?")
                or re.fullmatch(re.escape(ENDPOINT) + r"/[1-9][0-9]*", endpoint)):
            raise GitHubError("github_destination_refused")
        uncertain = method == "POST"
        if method not in ("GET", "POST") or (method == "POST" and endpoint != ENDPOINT):
            raise GitHubError("github_action_refused")
        request = Request(API_ROOT + endpoint, method=method,
                          data=json.dumps(payload, ensure_ascii=True).encode() if payload is not None else None,
                          headers={"Accept": "application/vnd.github+json", "Content-Type": "application/json",
                                   "X-GitHub-Api-Version": API_VERSION, "User-Agent": "romeo-mcp-issue-reporter",
                                   "Authorization": "Bearer " + self._token})
        try:
            with build_opener(NoRedirect()).open(request, timeout=timeout) as response:
                expected = 201 if uncertain else 200
                if response.status != expected:
                    raise GitHubError("github_status_unexpected", uncertain=uncertain)
                return _json(response.read(MAX_RESPONSE + 1), uncertain=uncertain)
        except HTTPError as exc:
            delay = 300
            try:
                delay = int(exc.headers.get("Retry-After", "300"))
                if exc.headers.get("X-RateLimit-Remaining") == "0":
                    delay = max(delay, int(exc.headers.get("X-RateLimit-Reset", "0")) - int(time.time()))
            except (ValueError, TypeError, AttributeError):
                pass
            exc.close()
            known_refusal = exc.code in (400, 401, 403, 404, 410, 422, 429)
            raise GitHubError(f"github_http_{exc.code}", uncertain=uncertain and not known_refusal,
                              retry_seconds=delay) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise GitHubError("github_connection_failed", uncertain=uncertain) from exc

    def _issue(self, value, digest: str, *, uncertain: bool = False) -> dict:
        if not isinstance(value, dict) or "pull_request" in value:
            raise GitHubError("github_issue_invalid", uncertain=uncertain)
        number = value.get("number")
        url = f"https://github.com/{REPOSITORY}/issues/{number}"
        body = value.get("body")
        if (type(number) is not int or number < 1 or not isinstance(value.get("html_url"), str)
                or value["html_url"].lower() != url.lower() or not isinstance(body, str)
                or marker(digest) not in body or not isinstance(value.get("title"), str)
                or value.get("state") not in ("open", "closed")):
            raise GitHubError("github_issue_invalid", uncertain=uncertain)
        return {"number": number, "url": url, "title": value["title"], "body": body, "state": value["state"]}

    def find(self, digest: str) -> dict | None:
        deadline = time.monotonic() + LOOKUP_TIMEOUT
        for page in range(1, MAX_PAGES + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise GitHubError("github_lookup_limit")
            rows = self.request("GET", ENDPOINT + f"?state=all&sort=created&direction=desc&per_page=100&page={page}",
                                timeout=min(REQUEST_TIMEOUT, remaining))
            if not isinstance(rows, list) or len(rows) > 100:
                raise GitHubError("github_response_invalid")
            for row in rows:
                if not isinstance(row, dict):
                    raise GitHubError("github_response_invalid")
                if "pull_request" not in row and isinstance(row.get("body"), str) and marker(digest) in row["body"]:
                    return self._issue(row, digest)
            if len(rows) < 100:
                return None
        # La recherche indexee de GitHub est eventual-consistent : elle ne peut
        # pas certifier l'absence d'un doublon. On refuse plutot une creation
        # si la lecture paginee de l'historique depasse le plafond.
        raise GitHubError("github_lookup_limit")

    def get(self, number: int, digest: str) -> dict:
        return self._issue(self.request("GET", ENDPOINT + f"/{number}"), digest)

    def create(self, title: str, body: str, digest: str) -> dict:
        value = self.request("POST", ENDPOINT, {"title": title, "body": body})
        return self._issue(value, digest, uncertain=True)


def marker(digest: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("Empreinte de rapport invalide.")
    return f"<!-- romeo-mcp-report:v1:{digest} -->"
