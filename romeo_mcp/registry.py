"""Registre local des jobs soumis.

Raison d'etre : le contexte d'un modele est volatil, pas ROMEO. Sans trace
locale, un modele qui perd son contexte perd aussi la trace des jobs qu'il a
lances (repertoire de travail, script exact, chemins des logs). Le registre
permet a `list_jobs` et `job_output` de retrouver tout cela apres coup.

SQLite, dans ``~/.romeo-mcp/jobs.db``.
"""

from __future__ import annotations

import os
import json
import sqlite3
import threading
import time
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id       TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    submitted_at REAL NOT NULL,
    partition    TEXT,
    arch         TEXT,
    workdir      TEXT,
    stdout_glob  TEXT,
    stderr_glob  TEXT,
    script       TEXT,
    last_state   TEXT,
    note         TEXT
);
CREATE INDEX IF NOT EXISTS jobs_submitted_at ON jobs(submitted_at DESC);
CREATE TABLE IF NOT EXISTS job_provenance (
    job_id TEXT PRIMARY KEY,
    payload TEXT NOT NULL
);
"""


def default_path() -> Path:
    override = os.environ.get("ROMEO_MCP_DB")
    if override:
        return Path(override)
    return Path.home() / ".romeo-mcp" / "jobs.db"


class Registry:
    """Acces concurrent-sur au registre des jobs."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else default_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def record(
        self,
        job_id: str,
        name: str,
        partition: str,
        arch: str,
        workdir: str,
        stdout_glob: str,
        stderr_glob: str,
        script: str,
        note: str = "",
        provenance: dict | None = None,
    ) -> None:
        payload = json.dumps(provenance, ensure_ascii=False) if provenance is not None else None
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO jobs (job_id, name, submitted_at, "
                "partition, arch, workdir, stdout_glob, stderr_glob, script, "
                "last_state, note) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    str(job_id),
                    name,
                    time.time(),
                    partition,
                    arch,
                    workdir,
                    stdout_glob,
                    stderr_glob,
                    script,
                    "SUBMITTED",
                    note,
                ),
            )
            if payload is not None:
                self._conn.execute("INSERT OR REPLACE INTO job_provenance VALUES (?, ?)",
                                   (str(job_id), payload))
            else:
                self._conn.execute("DELETE FROM job_provenance WHERE job_id = ?", (str(job_id),))

    def get_provenance(self, job_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute("SELECT payload FROM job_provenance WHERE job_id = ?",
                                     (str(job_id),)).fetchone()
        return json.loads(row[0]) if row else None

    def get(self, job_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (str(job_id),)
            ).fetchone()
        return dict(row) if row else None

    def recent(self, limit: int = 20) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM jobs ORDER BY submitted_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def set_state(self, job_id: str, state: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE jobs SET last_state = ? WHERE job_id = ?",
                (state, str(job_id)),
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()


_REGISTRY: Registry | None = None
_REGISTRY_LOCK = threading.Lock()


def registry() -> Registry:
    global _REGISTRY
    with _REGISTRY_LOCK:
        if _REGISTRY is None:
            _REGISTRY = Registry()
        return _REGISTRY
