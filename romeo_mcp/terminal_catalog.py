"""Global local inventory, indexed privately in memory; only bounded pages cross IO.

The source databases are never mutated. The index contains sanitized display
records, not scripts, SSH targets, checkpoint manifests or report bodies.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import time
import unicodedata

from . import terminal_data as data
from .terminal_cache import JsonFiles, database_signature, signature

VIEWS = ("jobs", "transfers", "reports", "alerts", "sessions")
SORTS = ("activity", "date", "state", "priority")
ACTIVE = {"RUNNING", "PENDING", "SUBMITTED", "CONFIGURING", "COMPLETING", "SUSPENDED",
          "RESIZING", "REQUEUED", "REQUEUE_FED", "REQUEUE_HOLD"}
ERROR = {"FAILED", "TIMEOUT", "CANCELLED", "NODE_FAIL", "OUT_OF_MEMORY", "BOOT_FAIL",
         "DEADLINE", "PREEMPTED", "LAUNCHFAILED", "PUBLICATION_UNKNOWN"}
JOB_LABELS = dict(zip(("RUNNING", "PENDING", "SUBMITTED", "CONFIGURING", "COMPLETING", "RESIZING",
                      "SUSPENDED", "REQUEUED", "REQUEUE_FED", "REQUEUE_HOLD", "COMPLETED", "FAILED",
                      "TIMEOUT", "CANCELLED", "NODE_FAIL", "OUT_OF_MEMORY", "BOOT_FAIL", "DEADLINE", "PREEMPTED"),
                     ("En cours", "En attente", "Soumis", "Préparation", "Finalisation", "Redimensionnement",
                      "Suspendu", "Remis en file", "Remis en file", "Remis en file", "Terminé", "Échec",
                      "Délai dépassé", "Annulé", "Nœud perdu", "Mémoire dépassée", "Démarrage échoué", "Date limite", "Préempté")))
TRANSFER_LABELS = {"prepared": "Préparé", "preparing": "Préparation", "running": "En cours",
                   "completed": "Terminé", "completed_unverified": "À vérifier", "cancelled": "Annulé",
                   "failed": "Échec", "launchFailed": "Échec"}
REPORT_LABELS = {"local_only": "Local", "publishing": "Envoi à vérifier", "published": "Publié",
                 "duplicate": "Déjà publié", "failed": "Échec", "publication_unknown": "Envoi incertain",
                 "rate_limited": "En attente"}


def normalize(value):
    return "".join(c for c in unicodedata.normalize("NFKD", value).lower()
                   if not unicodedata.combining(c))


def request(value=None):
    """Bound and whitelist requests even when the caller bypasses the CLI."""
    value = {} if value is None else value
    if not isinstance(value, dict) or any(key not in {"request_id", "queries", "pages", "sorts", "anchors", "force",
                                                    "job_stale_after", "transfer_stale_after", "collect", "detail_job", "progressive"} for key in value):
        raise ValueError("Requête de lecture incompatible")
    result = {"request_id": value.get("request_id", 0), "force": value.get("force", False),
              "collect": value.get("collect", True), "detail_job": value.get("detail_job", ""),
              "progressive": value.get("progressive", False),
              "job_stale_after": value.get("job_stale_after", 300),
              "transfer_stale_after": value.get("transfer_stale_after", 60)}
    if type(result["request_id"]) is not int or not 0 <= result["request_id"] <= 2**53:
        raise ValueError("Identifiant de lecture invalide")
    if type(result["force"]) is not bool:
        raise ValueError("Forçage de lecture invalide")
    if type(result["collect"]) is not bool or not isinstance(result["detail_job"], str) or len(result["detail_job"]) > 80:
        raise ValueError("Collecte ou dossier invalide")
    if type(result["progressive"]) is not bool:
        raise ValueError("Inventaire progressif invalide")
    for key in ("job_stale_after", "transfer_stale_after"):
        if type(result[key]) is not int or not 1 <= result[key] <= 86400:
            raise ValueError("Seuil de fraîcheur invalide")
    for key in ("queries", "pages", "sorts", "anchors"):
        supplied = value.get(key, {})
        if not isinstance(supplied, dict) or any(view not in VIEWS for view in supplied):
            raise ValueError("Préférences de lecture invalides")
        result[key] = {}
        for view in VIEWS:
            item = supplied.get(view, "" if key in {"queries", "anchors"} else 0 if key == "pages"
                                else "activity" if view == "jobs" else "priority" if view == "alerts" else "date")
            if ((key == "queries" and (not isinstance(item, str) or len(item) > 80 or data.text(item, 80) != item.strip()))
                    or (key == "pages" and (type(item) is not int or not 0 <= item <= 2**31))
                    or (key == "anchors" and (not isinstance(item, str) or len(item) > 200 or data.text(item, 200) != item.strip()))
                    or (key == "sorts" and item not in SORTS)):
                raise ValueError("Filtre, page ou tri invalide")
            result[key][view] = item.strip() if key in {"queries", "anchors"} else item
    return result


_SCHEMA = """
CREATE TABLE records(kind TEXT, id TEXT, name TEXT, state TEXT, label TEXT, state_key TEXT, searchable TEXT,
 date REAL, observed REAL, active INTEGER, failed INTEGER, unverified INTEGER,
 warning INTEGER, record TEXT, PRIMARY KEY(kind,id));
CREATE INDEX records_date ON records(kind,date DESC,id);
"""


class Catalog:
    def __init__(self, *, db: Path | None = None, limit=40, demo=False, progress=None):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Une page doit contenir entre 1 et 100 éléments")
        self.path = (db or data.registry_path()).expanduser().absolute() if not demo else None
        self.limit, self.demo = limit, demo
        self.index = sqlite3.connect(":memory:")
        self.index.row_factory = sqlite3.Row
        self.index.executescript(_SCHEMA)
        self.files = JsonFiles()
        self.stamps = {}
        self.source_warnings = {}
        self.automatic = None
        self.job_reads = 0
        self.progress = progress
        self.progress_at = time.monotonic()
        self.request_id = 0
        self.transfer_stamps = {}
        self.transfer_warnings = set()
        self.initialized = False
        self.partial = False
        self.current_query = None
        self.workspace_key = None
        self.workspace_value = None
        self.export_stamp = ()
        self.notifications = []
        self.runtime_value = None
        self.updates_value = None
        self.metadata_dirty = True
        self.metadata_warnings = []

    def _heartbeat(self, phase, processed, total=None):
        if self.progress is not None and time.monotonic() - self.progress_at >= 0.5:
            self.progress({"message": "progress", "request_id": self.request_id,
                           "phase": phase, "processed": processed, "total": total})
            self.progress_at = time.monotonic()
            if phase == "transfers" and self.partial and self.current_query["progressive"]:
                self.progress(self._snapshot(self.current_query, time.time(), partial=True))

    def close(self):
        self.index.close()

    def _replace(self, kind, rows):
        # Roll back this source if its iterator fails halfway through.
        previous = {row[0]: json.loads(row[1]) for row in self.index.execute("SELECT id,record FROM records WHERE kind='jobs'")} if kind == "jobs" else {}
        changes = []
        with self.index:
            self.index.execute("DELETE FROM records WHERE kind=?", (kind,))
            for number, row in enumerate(rows, 1):
                self._store(kind, row)
                old = previous.get(row["id"])
                if old is not None:
                    message = None
                    observed_at = row.get("observed_at")
                    if observed_at and old["state"] != row["state"] and (row["state"] in ERROR or row["state"] == "COMPLETED"):
                        message = JOB_LABELS.get(row["state"], row["state"])
                    proof, earlier = row.get("checkpoint") or {}, old.get("checkpoint") or {}
                    if proof.get("integrity_verified") is True and (earlier.get("generation") != proof.get("generation") or earlier.get("integrity_verified") is not True):
                        message = "Checkpoint vérifié · génération " + str(proof["generation"])
                        observed_at = proof.get("observed_at")
                    if message:
                        import hashlib
                        changes.append({"job_id": row["id"], "message": message, "observed_at": observed_at,
                            "key": hashlib.sha256((row["id"] + message + str(observed_at)).encode()).hexdigest()})
                self._heartbeat(kind, number)
        self.notifications = (self.notifications + changes)[-50:]

    def _store(self, kind, row):
        state = row["state"]
        upper = state.upper()
        active = state in ACTIVE if kind == "jobs" else state in {"running", "preparing"} if kind == "transfers" else False
        label = (JOB_LABELS if kind == "jobs" else TRANSFER_LABELS if kind == "transfers" else REPORT_LABELS).get(state, state if kind == "sessions" else "Inconnu")
        unverified = not row["result_validated"] and (state == "COMPLETED" if kind == "jobs"
            else state in {"completed", "completed_unverified"} if kind == "transfers" else False)
        validation = "Vérifié" if row["result_validated"] else "À vérifier" if unverified else "À venir" if active else "Non validé"
        name = row.get("name", row.get("summary", ""))
        fields = [row["id"], name, state, label, validation, row.get("partition", ""),
                  row.get("job_id", ""),
                  row.get("category", ""), row.get("local_path", ""), row.get("remote_path", ""),
                  row.get("direction", "")]
        if kind == "transfers":
            fields.append("vers ROMEO" if row["direction"] == "upload" else "depuis ROMEO" if row["direction"] == "download" else "")
        self.index.execute("INSERT OR REPLACE INTO records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (kind, row["id"], name, state, label, normalize(label), normalize(" ".join(fields)),
             row.get("observed_at") or row.get("submitted_at") or row.get("created_at"),
             row.get("observed_at"), int(active), int(upper in ERROR), int(unverified),
             int(upper in ACTIVE or upper in {"COMPLETED_UNVERIFIED", "RATE_LIMITED", "PUBLISHING"}),
             json.dumps(row, ensure_ascii=True, allow_nan=False)))

    def _sync_jobs(self, force):
        warnings = []
        try:
            stamp = database_signature(self.path)
            if force or self.stamps.get("jobs") != stamp:
                if stamp[0] is None and self._count("kind='jobs'"):
                    raise OSError("Registre disparu")
                self._replace("jobs", data.iter_jobs(self.path, None, warnings))
                self.job_reads += 1
                # A concurrent change forces a new read rather than poisoning the cache.
                if stamp == database_signature(self.path):
                    self.stamps["jobs"] = stamp
                self.source_warnings["jobs"] = warnings
        except (OSError, sqlite3.Error, ValueError):
            self.stamps.pop("jobs", None)
            self.source_warnings["jobs"] = ["Registre local indisponible ; dernières traces de jobs conservées."]

    def _sync_reports(self, force):
        from .issue_store import ReportStore
        warnings = []
        try:
            store = ReportStore()
            stamp = (*database_signature(store.path), os.environ.get("ROMEO_AUTO_ISSUES"))
            if force or self.stamps.get("reports") != stamp:
                if stamp[0] is None and self._count("kind='reports'"):
                    raise OSError("Historique disparu")
                saved = data.reports(1000)  # The report store itself is bounded to 1000 records.
                self._replace("reports", saved["items"])
                self.automatic = saved["automatic_enabled"]
                if stamp == (*database_signature(store.path), os.environ.get("ROMEO_AUTO_ISSUES")):
                    self.stamps["reports"] = stamp
                self.source_warnings["reports"] = warnings
        except (OSError, sqlite3.Error, ValueError, TypeError, KeyError):
            self.stamps.pop("reports", None)
            self.automatic = None
            self.source_warnings["reports"] = ["Historique local des rapports inaccessible ; dernières traces conservées."]

    def _sync_transfers(self, force):
        try:
            if force:
                self.files.clear()
            root = self.path.parent / "transfers"
            if not root.is_dir():
                if self._count("kind='transfers'"):
                    raise OSError("Inventaire disparu")
                directories = ()
            else:
                directories = self.files.directories(root)
            stamps = {}
            errors = self.transfer_warnings.copy()
            with self.index:
                for number, directory in enumerate(directories, 1):
                    identity = directory.name
                    stamp = tuple(signature(directory / name) for name in ("plan.json", "status.json", "cancel.json"))
                    if force or self.transfer_stamps.get(identity) != stamp:
                        try:
                            self._store("transfers", data.read_transfer(directory, self.files))
                            errors.discard(identity)
                        except (OSError, ValueError, TypeError, KeyError):
                            self.index.execute("DELETE FROM records WHERE kind='transfers' AND id=?", (identity,))
                            errors.add(identity)
                        # A concurrent replacement is retried next time.
                        if stamp == tuple(signature(directory / name) for name in ("plan.json", "status.json", "cancel.json")):
                            stamps[identity] = stamp
                    else:
                        stamps[identity] = stamp
                    self._heartbeat("transfers", number, len(directories))
                present = {directory.name for directory in directories}
                saved_ids = {row[0] for row in self.index.execute("SELECT id FROM records WHERE kind='transfers'")}
                for removed in saved_ids - present:
                    self.index.execute("DELETE FROM records WHERE kind='transfers' AND id=?", (removed,))
                errors.intersection_update(present)
            self.transfer_stamps = stamps
            self.transfer_warnings = errors
            self.source_warnings["transfers"] = ["Un dossier de transfert est incomplet ou illisible."] if errors else []
        except (OSError, sqlite3.Error, ValueError):
            self.source_warnings["transfers"] = ["Inventaire local des transferts inaccessible ; dernières traces conservées."]

    def _count(self, where="1", parameters=()):
        return self.index.execute("SELECT COUNT(*) FROM records WHERE " + where, parameters).fetchone()[0]

    def _attention_sql(self, query, at):
        return ("(failed=1 OR unverified=1 OR (active=1 AND "
                "(observed IS NULL OR observed<=0 OR observed>? OR observed<?-"
                "CASE WHEN kind='jobs' THEN ? ELSE ? END)))",
                (at + 5, at, query["job_stale_after"], query["transfer_stale_after"]))

    def _page(self, view, query, at):
        attention, attention_params = self._attention_sql(query, at)
        base, base_params = (attention, attention_params) if view == "alerts" else ("kind=?", (view,))
        # Freshness is computed at request time, rather than frozen in the cache.
        freshness = "CASE WHEN observed IS NULL OR observed<=0 THEN ' absent' WHEN observed>? THEN ' date future' WHEN observed<?-CASE WHEN kind='jobs' THEN ? ELSE ? END THEN ' ancien' ELSE ' recent' END"
        where = base + " AND instr(searchable || " + freshness + ",?)>0"
        from .terminal_filters import compile_query
        try:
            filters, parameters_filter, words = compile_query(query["queries"][view], normalize)
        except ValueError as exc:
            filters, parameters_filter, words = "0", (), ""
            self.filter_warnings.append("Filtre " + view + " : " + str(exc))
        where += " AND " + filters
        parameters = (*base_params, at + 5, at, query["job_stale_after"], query["transfer_stale_after"], normalize(words), *parameters_filter)
        total = self._count(base, base_params)
        matched = self._count(where, parameters)
        pages = max(1, (matched + self.limit - 1) // self.limit)
        page = min(query["pages"][view], pages - 1)
        priority = "CASE WHEN failed=1 THEN 0 WHEN " + attention + " THEN 1 WHEN active=1 OR warning=1 THEN 2 ELSE 3 END"
        sort = query["sorts"][view]
        order = {"activity": "active DESC, failed DESC, date DESC, id",
                 "date": "date DESC, id", "state": "state_key, date DESC, id",
                 "priority": priority + ", date DESC, id"}[sort]
        order_params = attention_params if sort == "priority" else ()
        anchor = query["anchors"][view]
        if anchor:
            if view == "alerts":
                anchor_kind, separator, anchor_id = anchor.partition(":")
                if not separator or anchor_kind not in VIEWS[:3]:
                    raise ValueError("Cible d'alerte invalide")
            else:
                anchor_kind, anchor_id = view, anchor
            position = self.index.execute("SELECT position FROM (SELECT kind,id,ROW_NUMBER() OVER (ORDER BY "
                + order + ")-1 AS position FROM records WHERE " + where + ") WHERE kind=? AND id=?",
                (*order_params, *parameters, anchor_kind, anchor_id)).fetchone()
            if position is not None:
                page = position[0] // self.limit
        rows = self.index.execute("SELECT * FROM records WHERE " + where + " ORDER BY " + order + " LIMIT ? OFFSET ?",
                                  (*parameters, *order_params, self.limit, page * self.limit)).fetchall()
        if view == "alerts":
            result = []
            for row in rows:
                reason = row["label"] if row["failed"] else ("Résultat à vérifier" if row["kind"] == "jobs" else "Copie à vérifier") if row["unverified"] else "Observation ancienne ou absente"
                result.append({"kind": row["kind"], "id": row["id"], "name": row["name"], "state": row["state"],
                               "reason": reason, "observed_at": row["observed"]})
        else:
            result = [json.loads(row["record"]) for row in rows]
        return result, {"page": page, "pages": pages, "loaded": len(result), "matched": matched,
                        "total": total, "page_size": self.limit}

    def snapshot(self, value=None):
        query = request(value)
        self.current_query = query
        self.request_id = query["request_id"]
        self.progress_at = time.monotonic()
        warnings = []
        at = time.time()
        if self.demo:
            demo = data.demo_snapshot(100)
            requested = {"nodes": 2, "tasks_per_node": 4, "cpus_per_task": 1, "omp_threads": 1}
            for index, job in enumerate(demo["jobs"]):
                job["resources"] = {"requested": requested if index in (0, 3) else
                                    {"nodes": 1, "tasks": 1, "cpus_per_task": 8, "omp_threads": 8} if index == 1 else {},
                                    "observed": {"nodes": 2} if index == 0 else {}}
            demo["transfers"].append({**demo["transfers"][1], "id": "d" * 32,
                                      "name": "output-unverified.tar", "local_path": "output-unverified.tar",
                                      "result_validated": False})
            for kind in VIEWS[:3]:
                self._replace(kind, demo["reports"]["items"] if kind == "reports" else demo[kind])
            runtime, updates = demo["runtime"], demo["updates"]
            self.automatic = demo["reports"]["automatic_enabled"]
        else:
            if query["collect"] or query["force"] or not self.initialized:
                self.metadata_dirty = True
                self._sync_jobs(query["force"])
                self.partial = not self.initialized
                if self.partial and self.progress is not None and query["progressive"]:
                    self.progress(self._snapshot(query, at, partial=True))
                self._sync_transfers(query["force"])
                self._sync_reports(query["force"])
                try:
                    self.export_stamp = tuple((item.name, signature(item)) for item in
                        self.files.directories(self.path.parent / "checkpoint-exports", files=True))
                except OSError:
                    self.workspace_key = None
                from .terminal_workspace import sessions
                stamp = database_signature(self.path)
                if self.stamps.get("sessions") != stamp or query["force"]:
                    try:
                        self._replace("sessions", sessions(self.path))
                        self.stamps["sessions"] = stamp
                        self.source_warnings["sessions"] = []
                    except (OSError, sqlite3.Error, ValueError):
                        self.source_warnings["sessions"] = ["Historique des sessions indisponible."]
                self.initialized = True
                self.partial = False
        return self._snapshot(query, at)

    def _snapshot(self, query, at, *, partial=False):
        self.filter_warnings = []
        warnings = [item for messages in self.source_warnings.values() for item in messages]
        if self.demo:
            demo = data.demo_snapshot(100)
            runtime, updates = demo["runtime"], demo["updates"]
            from .terminal_demo import sessions as demo_sessions
            self._replace("sessions", demo_sessions(at))
        else:
            if self.metadata_dirty or self.runtime_value is None:
                self.metadata_warnings = []
                self.runtime_value = data.read_runtime(self.path, self.metadata_warnings)
                self.updates_value = data.read_updates(self.metadata_warnings)
                self.metadata_dirty = False
            warnings.extend(self.metadata_warnings)
            runtime, updates = self.runtime_value, self.updates_value
        coverage, items = {}, {}
        for view in VIEWS:
            items[view], coverage[view] = self._page(view, query, at)
        recent = [json.loads(row[0]) for row in self.index.execute(
            "SELECT record FROM records WHERE kind='jobs' ORDER BY date DESC,id LIMIT 4")]
        detail = query["detail_job"]
        if not any(job["id"] == detail for job in items["jobs"]):
            detail = items["jobs"][0]["id"] if items["jobs"] else ""
        workspace = {}
        if not partial and not self.demo:
            from .terminal_workspace import workspace as read_workspace
            key = (self.stamps.get("jobs"), detail, tuple(self.transfer_stamps.items()), self.export_stamp)
            if self.workspace_key != key:
                try:
                    self.workspace_value = read_workspace(self.path, detail, self.files, self.index)
                    self.workspace_key = key
                except (OSError, sqlite3.Error, ValueError):
                    self.workspace_value = {}
                    warnings.append("Dossier de calcul indisponible.")
            workspace = self.workspace_value or {}
        elif self.demo:
            from .terminal_demo import workspace as demo_workspace
            workspace = demo_workspace(detail, at)
        return {"schema": 3, "partial": partial, "request_id": query["request_id"], "generated_at": at, "demo": self.demo,
                "runtime": runtime, "jobs": items["jobs"], "transfers": items["transfers"],
                "reports": {"automatic_enabled": self.automatic, "items": items["reports"]},
                "updates": updates, "warnings": list(dict.fromkeys(warnings + self.filter_warnings))[:100],
                "attention": items["alerts"], "recent_jobs": recent, "coverage": coverage,
                "workspace": workspace, "sessions": items["sessions"],
                "notifications": self.notifications,
                "active_jobs": self._count("kind='jobs' AND active=1")}


def snapshot(*, db=None, limit=40, demo=False, query=None):
    catalog = Catalog(db=db, limit=limit, demo=demo)
    try:
        return catalog.snapshot(query)
    finally:
        catalog.close()
