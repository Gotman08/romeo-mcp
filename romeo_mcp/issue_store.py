"""Registre prive des rapports MCP : autorisation, doublons et tentatives."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import time

from .config import config_path
from .updates import REPOSITORY, UpdateError, file_lock

STATES = {"local_only", "publishing", "published", "duplicate", "failed", "publication_unknown", "rate_limited"}
MAX_REPORTS = 1000
MAX_PER_DAY = 5
MIN_INTERVAL = 60


def fingerprint(document: dict) -> str:
    return hashlib.sha256(json.dumps(document, ensure_ascii=True, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def validate_id(report_id: str) -> str:
    if not isinstance(report_id, str) or not re.fullmatch(r"[a-f0-9]{32}", report_id):
        raise ValueError("report_id doit contenir exactement 32 caracteres hexadecimaux.")
    return report_id


class PublicationDelay(ValueError):
    def __init__(self, retry_after: float):
        super().__init__("Publication limitee : conserver le rapport local et attendre retry_after.")
        self.retry_after = retry_after


class ReportStore:
    def __init__(self, root: Path | None = None):
        override = os.environ.get("ROMEO_REPORTS_DIR", "").strip()
        self.root = (root or (Path(override).expanduser() if override else config_path().parent / "issue-reports")).resolve()
        if any((p / ".git").exists() for p in (self.root, *self.root.parents)):
            raise ValueError("ROMEO_REPORTS_DIR doit se trouver hors des depots Git.")
        self.path = self.root / "reports.sqlite3"

    @contextmanager
    def connect(self, write: bool = False):
        if self.path.is_symlink():
            raise ValueError("Le registre de rapports ne doit pas etre un lien symbolique.")
        if not write and not self.path.exists():
            yield None
            return
        db = None
        try:
            if write:
                self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
                db = sqlite3.connect(self.path, timeout=0.2)
            else:
                db = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=0.2)
                db.execute("PRAGMA query_only=ON")
            db.row_factory = sqlite3.Row
            if write:
                db.execute("PRAGMA secure_delete=ON")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1) or (not write and version != 1):
                raise ValueError("Version du registre de rapports inconnue ; aucun envoi effectue.")
            if write and version == 0:
                with db:
                    db.execute("CREATE TABLE IF NOT EXISTS policy (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
                    db.execute("CREATE TABLE IF NOT EXISTS reports ("
                               "report_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, document TEXT NOT NULL, "
                               "state TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL, "
                               "occurrences INTEGER NOT NULL DEFAULT 1, attempts INTEGER NOT NULL DEFAULT 0, "
                               "issue_number INTEGER, issue_url TEXT, last_error TEXT, retry_after REAL NOT NULL DEFAULT 0)")
                    db.execute("CREATE TABLE IF NOT EXISTS attempts (timestamp REAL NOT NULL, report_id TEXT NOT NULL)")
                    db.execute("CREATE INDEX IF NOT EXISTS attempts_time ON attempts(timestamp)")
                    db.execute("PRAGMA user_version=1")
            with db:
                yield db
        except (sqlite3.Error, OSError) as exc:
            raise ValueError("Registre de rapports inaccessible ; aucun succes de publication ne peut etre affirme.") from exc
        finally:
            if db is not None:
                db.close()

    def policy(self) -> dict:
        with self.connect() as db:
            values = dict(db.execute("SELECT key, value FROM policy").fetchall()) if db else {}
        automatic = values.get("automatic", "0")
        try:
            retry_after = float(values.get("retry_after", "0"))
        except ValueError as exc:
            raise ValueError("Politique de rapports illisible.") from exc
        if automatic not in ("0", "1") or not math.isfinite(retry_after) or retry_after < 0:
            raise ValueError("Politique de rapports illisible.")
        return {"saved_automatic": automatic == "1", "retry_after": retry_after}

    def configure(self, automatic: bool) -> None:
        with self.connect(True) as db:
            db.execute("INSERT OR REPLACE INTO policy VALUES ('automatic', ?)", ("1" if automatic else "0",))

    def throttle(self, retry_after: float) -> None:
        with self.connect(True) as db:
            db.execute("INSERT OR REPLACE INTO policy VALUES ('retry_after', ?)", (str(retry_after),))

    def save(self, document: dict) -> dict:
        digest = fingerprint(document)
        report_id = digest[:32]
        now = time.time()
        with self.connect(True) as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT 1 FROM reports WHERE report_id=?", (report_id,)).fetchone()
            if existing:
                db.execute("UPDATE reports SET occurrences=occurrences+1 WHERE report_id=?", (report_id,))
            else:
                if db.execute("SELECT COUNT(*) FROM reports").fetchone()[0] >= MAX_REPORTS:
                    raise ValueError("Registre plein (1000 rapports) ; archiver les rapports avant de continuer.")
                db.execute("INSERT INTO reports (report_id, fingerprint, document, state, created_at, updated_at) "
                           "VALUES (?, ?, ?, 'local_only', ?, ?)",
                           (report_id, digest, json.dumps(document, ensure_ascii=True), now, now))
        return self.get(report_id)

    def _decode(self, row) -> dict:
        value = dict(row)
        try:
            raw = value.pop("document")
            if len(raw) > 65536:
                raise ValueError()
            document = json.loads(raw)
            if not isinstance(document, dict) or document.get("schema") != 1 or document.get("repository") != REPOSITORY:
                raise ValueError()
            digest = fingerprint(document)
            if digest != value["fingerprint"] or digest[:32] != value["report_id"] or value["state"] not in STATES:
                raise ValueError()
            if value["state"] in ("published", "duplicate"):
                number = value["issue_number"]
                if not isinstance(number, int) or number < 1 or value["issue_url"] != f"https://github.com/{REPOSITORY}/issues/{number}":
                    raise ValueError()
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError("Rapport local altere ou incompatible ; aucun envoi effectue.") from exc
        value["report"] = document
        value["result_validated"] = value["state"] in ("published", "duplicate")
        return value

    def get(self, report_id: str) -> dict:
        validate_id(report_id)
        with self.connect() as db:
            row = db.execute("SELECT * FROM reports WHERE report_id=?", (report_id,)).fetchone() if db else None
        if row is None:
            raise ValueError("Rapport local introuvable.")
        return self._decode(row)

    def recent(self, limit: int = 20) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM reports ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall() if db else []
        return [self._decode(row) for row in rows]

    def delete_local(self, report_id: str = "") -> int:
        """Supprime le contenu local choisi ; consentement et quotas restent distincts."""
        if report_id:
            validate_id(report_id)
        with self.publication_lock(), self.connect(True) as db:
            # Les dates suffisent au quota ; ne pas conserver l'empreinte du
            # texte prive dans l'historique des tentatives apres suppression.
            if report_id:
                db.execute("UPDATE attempts SET report_id='' WHERE report_id=?", (report_id,))
            else:
                db.execute("UPDATE attempts SET report_id=''")
            cursor = db.execute("DELETE FROM reports WHERE report_id=?", (report_id,)) if report_id else db.execute("DELETE FROM reports")
            return cursor.rowcount

    def update(self, report_id: str, state: str, *, issue_number=None, issue_url=None,
               last_error=None, retry_after: float = 0) -> dict:
        validate_id(report_id)
        if state not in STATES:
            raise ValueError("Etat de publication inconnu.")
        with self.connect(True) as db:
            db.execute("UPDATE reports SET state=?, updated_at=?, issue_number=?, issue_url=?, "
                       "last_error=?, retry_after=? WHERE report_id=?",
                       (state, time.time(), issue_number, issue_url, last_error, retry_after, report_id))
        return self.get(report_id)

    def start_attempt(self, report_id: str) -> None:
        now = time.time()
        with self.connect(True) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM attempts WHERE timestamp<?", (now - 86400,))
            count, last, first = db.execute("SELECT COUNT(*), MAX(timestamp), MIN(timestamp) FROM attempts").fetchone()
            if count >= MAX_PER_DAY:
                raise PublicationDelay(first + 86400)
            if last is not None and now < last + MIN_INTERVAL:
                raise PublicationDelay(last + MIN_INTERVAL)
            db.execute("INSERT INTO attempts VALUES (?, ?)", (now, report_id))
            db.execute("UPDATE reports SET state='publishing', attempts=attempts+1, updated_at=?, "
                       "last_error=NULL, retry_after=0 WHERE report_id=?", (now, report_id))

    @contextmanager
    def publication_lock(self):
        if (self.root / "publication.lock").is_symlink():
            raise ValueError("Le verrou de publication ne doit pas etre un lien symbolique.")
        try:
            with file_lock(self.root / "publication.lock"):
                yield
        except UpdateError as exc:
            raise ValueError("Une publication de rapport est deja en cours ; relire mcp_issue_status.") from exc
