"""Registre local des jobs soumis.

Raison d'etre : le contexte d'un modele est volatil, pas ROMEO. Sans trace
locale, un modele qui perd son contexte perd aussi la trace des jobs qu'il a
lances (repertoire de travail, script exact, chemins des logs). Le registre
permet a `list_jobs` et `job_log_tail` de retrouver tout cela apres coup.

SQLite, dans ``~/.romeo-mcp/jobs.db``.
"""

from __future__ import annotations

import os
import atexit
import hashlib
import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path

PLAN_TTL_SECONDS = 24 * 60 * 60


def _event_key(payload: dict) -> str:
    """Keep state/proof changes, not a new event for every elapsed-time tick."""
    fields = ("state", "slurm_state", "result_validated", "resume_validated", "service_readiness_observed",
              "checkpoint_after_signal_verified", "latest_checkpoint", "checkpoint", "protection",
              "application_completion_observed", "exit_code", "cpu_efficiency_pct", "max_rss_mb", "log_sha256",
              "dependencies_remaining")
    return json.dumps({key: payload[key] for key in fields if key in payload}, sort_keys=True)

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
CREATE TABLE IF NOT EXISTS prepared_submissions (
    plan_id TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    payload TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    state TEXT NOT NULL,
    result TEXT
);
CREATE TABLE IF NOT EXISTS report_snapshots (
    report_id TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    sha256 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS job_observations (
    job_id TEXT NOT NULL,
    target TEXT NOT NULL,
    observed_at REAL NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (job_id, target)
);
CREATE TABLE IF NOT EXISTS observation_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL, target TEXT NOT NULL, observed_at REAL NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS observation_events_job ON observation_events(job_id, event_id DESC);
CREATE TABLE IF NOT EXISTS artifact_links (
    job_id TEXT NOT NULL, kind TEXT NOT NULL, artifact_id TEXT NOT NULL,
    created_at REAL NOT NULL, PRIMARY KEY(job_id,kind,artifact_id)
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
        os.chmod(self.path, 0o600)
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

    def save_observation(self, job_id: str, target: dict, payload: dict) -> dict:
        """Retain the latest observed state across SSH and MCP restarts."""
        observed = time.time()
        key = json.dumps(target, sort_keys=True)
        encoded = json.dumps(payload, ensure_ascii=False)
        with self._lock, self._conn:
            self._conn.execute("INSERT OR REPLACE INTO job_observations VALUES (?, ?, ?, ?)",
                               (str(job_id), key, observed, encoded))
            previous = self._conn.execute(
                "SELECT payload FROM observation_events WHERE job_id=? AND target=? ORDER BY event_id DESC LIMIT 1",
                (str(job_id), key)).fetchone()
            if previous is None or _event_key(json.loads(previous[0])) != _event_key(payload):
                self._conn.execute("INSERT INTO observation_events(job_id,target,observed_at,payload) VALUES(?,?,?,?)",
                                   (str(job_id), key, observed, encoded))
                self._conn.execute("DELETE FROM observation_events WHERE job_id=? AND event_id NOT IN "
                                   "(SELECT event_id FROM observation_events WHERE job_id=? ORDER BY event_id DESC LIMIT 256)",
                                   (str(job_id), str(job_id)))
                self._conn.execute("DELETE FROM observation_events WHERE event_id < "
                                   "(SELECT MAX(event_id)-200000 FROM observation_events)")
        return {"observed_at": observed, "target": target, "source": "slurm", "current_state_observed": True}

    def link_artifact(self, job_id: str, kind: str, artifact_id: str) -> None:
        """Record an explicit association; matching filenames are never evidence."""
        if kind not in {"transfer", "report", "result", "job"} or not artifact_id or len(artifact_id) > 180:
            raise ValueError("Association d'artefact invalide")
        with self._lock, self._conn:
            if not self._conn.execute("SELECT 1 FROM jobs WHERE job_id=?", (str(job_id),)).fetchone():
                raise ValueError("Job local introuvable")
            self._conn.execute("INSERT OR IGNORE INTO artifact_links VALUES(?,?,?,?)",
                               (str(job_id), kind, str(artifact_id), time.time()))

    def record_array_task(self, parent_id: str, identifier: str) -> None:
        import re
        if not re.fullmatch(re.escape(parent_id) + r"_\d+", identifier):
            raise ValueError("Sous-job Slurm invalide")
        with self._lock, self._conn:
            self._conn.execute("INSERT OR IGNORE INTO jobs SELECT ?,name,submitted_at,partition,arch,workdir,"
                "stdout_glob,stderr_glob,script,last_state,note FROM jobs WHERE job_id=?", (identifier,parent_id))

    def observation(self, job_id: str, target: dict | None = None) -> dict | None:
        with self._lock:
            if target is None:
                row = self._conn.execute("SELECT * FROM job_observations WHERE job_id=? ORDER BY observed_at DESC LIMIT 1", (str(job_id),)).fetchone()
            else:
                row = self._conn.execute("SELECT * FROM job_observations WHERE job_id=? AND target=?",
                                         (str(job_id), json.dumps(target, sort_keys=True))).fetchone()
        if row is None:
            return None
        return {"job_id": str(job_id), "target": json.loads(row["target"]), "observed_at": row["observed_at"],
                "age_seconds": max(0, time.time() - row["observed_at"]), "current_state_observed": False,
                "result": json.loads(row["payload"])}

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def prepare_submission(self, payload: dict) -> dict:
        """Conserve le contenu exact du plan, independamment du processus MCP."""
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        plan_id, created = uuid.uuid4().hex, time.time()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO prepared_submissions VALUES (?, ?, ?, ?, 'ready', NULL)",
                (plan_id, created, encoded, digest))
        return {"plan_id": plan_id, "plan_sha256": digest, "expires_at": created + PLAN_TTL_SECONDS}

    def prepared_submission(self, plan_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM prepared_submissions WHERE plan_id = ?", (plan_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        if hashlib.sha256(result["payload"].encode("utf-8")).hexdigest() != result["sha256"]:
            raise ValueError("Plan altere : prepare un nouveau plan avant de soumettre.")
        result["payload"] = json.loads(result["payload"])
        result["result"] = json.loads(result["result"]) if result["result"] else None
        return result

    def claim_submission(self, plan_id: str) -> bool:
        """Une seule tentative, y compris entre deux processus et apres un crash."""
        with self._lock, self._conn:
            cursor = self._conn.execute(
                "UPDATE prepared_submissions SET state = 'submitting' "
                "WHERE plan_id = ? AND state = 'ready' AND created_at > ?",
                (plan_id, time.time() - PLAN_TTL_SECONDS))
            return cursor.rowcount == 1

    def update_submission(self, plan_id: str, state: str, result: dict) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE prepared_submissions SET state = ?, result = ? WHERE plan_id = ?",
                (state, json.dumps(result, ensure_ascii=False), plan_id))

    def save_report(self, report: dict) -> dict:
        """Enregistre un releve immuable ; chaque nouvelle collecte a son identifiant."""
        report_id = uuid.uuid4().hex
        payload = json.dumps(report, ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256(payload.encode('utf-8')).hexdigest()
        with self._lock, self._conn:
            self._conn.execute('INSERT INTO report_snapshots VALUES (?, ?, ?)', (report_id, payload, digest))
        return {'report_id': report_id, 'report_sha256': digest, 'created_at': report['created_at'],
                'job_id': report['job_id'], 'storage': str(self.path)}

    def get_report(self, report_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute('SELECT payload, sha256 FROM report_snapshots WHERE report_id = ?',
                                     (report_id,)).fetchone()
        if row is None:
            return None
        if hashlib.sha256(row['payload'].encode('utf-8')).hexdigest() != row['sha256']:
            raise ValueError('Releve altere : nouvelle collecte necessaire.')
        return {'report_id': report_id, 'report_sha256': row['sha256'], 'report': json.loads(row['payload'])}


_REGISTRY: Registry | None = None
_REGISTRY_LOCK = threading.Lock()


def registry() -> Registry:
    global _REGISTRY
    with _REGISTRY_LOCK:
        if _REGISTRY is None:
            _REGISTRY = Registry()
            atexit.register(_REGISTRY.close)
        return _REGISTRY
