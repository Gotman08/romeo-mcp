"""Read-only, bounded calculation dossiers. Every link has recorded provenance."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3

from . import terminal_data as data
from .terminal_evidence import number, checkpoint
from .privacy import redact_text
from .checkpoint_protocol import digest

JOB_ID = re.compile(r"\d+(?:_(?:\d+|\[[\d,:%-]+\]))?\Z")


def decode(raw):
    if not isinstance(raw, str) or len(raw) > 65536:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except ValueError:
        return {}


def tables(connection):
    return {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def connect(path):
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0.2)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def source(target):
    return "source-" + hashlib.sha256(str(target).encode()).hexdigest()[:8]


def membership(script, identifier):
    array = re.search(r"(?m)^#SBATCH\s+--array(?:=|\s+)([\d,:%-]+)\s*$", script or "")
    dependency = re.search(r"(?m)^#SBATCH\s+--dependency(?:=|\s+)([A-Za-z0-9_:,?]+)\s*$", script or "")
    parent = identifier.split("_", 1)[0] if "_" in identifier else None
    return {"array_parent": parent, "array_spec": array.group(1) if array else "",
            "dependencies": data.text(dependency.group(1), 180) if dependency else ""}


def workspace(path, identifier, files, index):
    empty = {"job_id": identifier or "", "links": [], "events": [], "members": [],
             "efficiency": {}, "recovery": {}, "logs": None, "group": {}}
    if not identifier or not JOB_ID.fullmatch(identifier) or not path.is_file():
        return empty
    connection = connect(path)
    try:
        available = tables(connection)
        record = connection.execute("SELECT * FROM jobs WHERE job_id=?", (identifier,)).fetchone()
        if record is None:
            return empty
        latest_checkpoint = {}
        empty["group"] = membership(record["script"] if "script" in record.keys() else "", identifier)
        if "job_observations" in available:
            current = connection.execute("SELECT observed_at,payload,target FROM job_observations WHERE job_id=? ORDER BY observed_at DESC LIMIT 1",(identifier,)).fetchone()
            observed_job = decode(current["payload"]) if current else {}
            if observed_job.get("job_id")==identifier and observed_job.get("ok") is True and observed_job.get("scope","job")=="job":
                remaining = observed_job.get("dependencies_remaining")
                empty["group"].update(remaining_dependencies=data.text(remaining,1000) if isinstance(remaining,str) else None,
                    dependencies_observed_at=current["observed_at"],dependencies_source=source(current["target"]))
            for prefix in ("efficiency:", "logs:", "checkpoint:"):
                row = connection.execute("SELECT observed_at,substr(payload,1,65537) AS payload,target FROM job_observations "
                    "WHERE job_id=? ORDER BY observed_at DESC LIMIT 1", (prefix + identifier,)).fetchone()
                value = decode(row["payload"]) if row else {}
                if value.get("job_id") != identifier:
                    continue
                if prefix == "efficiency:" and value.get("ok") is True:
                    fields = ("alloc_cpus", "alloc_gpus", "elapsed_seconds", "cpu_seconds_used", "cpu_seconds_reserved",
                              "cpu_efficiency_pct", "max_rss_mb", "req_mem_mb", "mem_efficiency_pct", "gpu_utilization_pct")
                    empty["efficiency"] = {key: number(value.get(key)) for key in fields}
                    empty["efficiency"].update(observed_at=row["observed_at"], source=source(row["target"]))
                elif prefix == "logs:" and value.get("ok") is True:
                    content = value.get("content", "")
                    if isinstance(content, str):
                        empty["logs"] = {"content": "\n".join(data.text(line, 240) for line in
                            redact_text(content)[-8000:].splitlines()[-80:]), "observed_at": row["observed_at"],
                            "stream": data.text(value.get("stream")), "truncated": value.get("truncated") is True,
                            "source": source(row["target"])}
                elif prefix == "checkpoint:":
                    try:
                        proof = checkpoint(row["payload"], identifier)
                    except (ValueError, TypeError, KeyError):
                        proof = None
                    if proof:
                        latest_checkpoint = value.get("latest_checkpoint") or value.get("checkpoint") or {}
                        empty["recovery"] = {"complete": True if proof["integrity_verified"] else None,
                            "integrity": proof["integrity_verified"], "compatible": True if proof["integrity_verified"] else None,
                            "independent_backup": None, "resume_observed": value.get("resume_validated") if type(value.get("resume_validated")) is bool else None,
                            "step": proof["step"], "generation": proof["generation"], "world_size": proof["world_size"],
                            "observed_at": proof["observed_at"], "source": source(row["target"])}
        if "observation_events" in available:
            rows = connection.execute("SELECT job_id,target,observed_at,substr(payload,1,65537) AS payload FROM observation_events "
                "WHERE job_id IN (?,?,?,?) ORDER BY event_id DESC LIMIT 48",
                (identifier, "checkpoint:" + identifier, "efficiency:" + identifier, "logs:" + identifier))
            for row in rows:
                value = decode(row["payload"])
                if value.get("job_id") != identifier:
                    continue
                kind = row["job_id"].split(":", 1)[0] if ":" in row["job_id"] else "slurm"
                proof = value.get("latest_checkpoint") or value.get("checkpoint") or {}
                empty["events"].append({"kind": kind, "state": data.text(value.get("state", kind)),
                    "observed_at": row["observed_at"], "source": source(row["target"]),
                    "generation": number(proof.get("generation"), integer=True) if isinstance(proof, dict) else None,
                    "resume_observed": value.get("resume_validated") is True})
        links = []
        if "artifact_links" in available:
            links.extend((row[0], row[1], "association explicite") for row in connection.execute(
                "SELECT kind,artifact_id FROM artifact_links WHERE job_id=? ORDER BY created_at DESC LIMIT 80", (identifier,)))
        if "report_snapshots" in available:
            for row in connection.execute("SELECT report_id,payload,sha256 FROM report_snapshots ORDER BY rowid DESC LIMIT 1000"):
                value = decode(row["payload"])
                if value.get("job_id") == identifier and hashlib.sha256(row["payload"].encode()).hexdigest() == row["sha256"]:
                    links.append(("result", row["report_id"], "relevé signé"))
        for directory in files.directories(path.parent / "checkpoint-exports", files=True):
            if not re.fullmatch(r"[a-f0-9]{32}\.json", directory.name):
                continue
            try:
                export = files.read(directory)
                signed = {key: value for key, value in export.items() if key != "sha256"}
                if export.get("job_id") != identifier or export.get("sha256") != digest(signed):
                    continue
                transfer_id = export.get("transfer_id")
                if not isinstance(transfer_id, str) or not re.fullmatch(r"[a-f0-9]{32}", transfer_id):
                    continue
                transfer = index.execute("SELECT record FROM records WHERE kind='transfers' AND id=?", (transfer_id,)).fetchone()
                if transfer is None:
                    continue
                plan = files.read(path.parent / "transfers" / transfer_id / "plan.json")
                if plan.get("sha256") != export.get("transfer_sha256"):
                    continue
                links.append(("transfer", transfer_id, "export de checkpoint signé"))
                saved = files.read(directory.with_suffix(".verified.json"))
                proof = export.get("checkpoint") or {}
                if (saved.get("export_sha256") == export["sha256"] and saved.get("manifest_sha256") == proof.get("manifest_sha256")
                        and saved.get("independent_backup") is True and saved.get("checkpoint_integrity_verified") is True
                        and data.timestamp(saved.get("verified_at")) is not None
                        and json.loads(transfer["record"])["state"] in {"completed", "completed_unverified"}
                        and empty["recovery"].get("integrity") is True
                        and all(latest_checkpoint.get(key) == proof.get(key) for key in
                                ("manifest_sha256", "generation", "run_id", "world_size", "binding_sha256"))):
                    empty["recovery"]["independent_backup"] = True
            except (OSError, ValueError, TypeError, KeyError):
                continue
        distinct = {}
        for kind, artifact_id, basis in links:
            distinct.setdefault((kind,artifact_id),basis)
        empty["links_total"] = len(distinct)
        for (kind, artifact_id), basis in list(distinct.items())[:100]:
            mapped = {"transfer": "transfers", "report": "reports", "job": "jobs"}.get(kind)
            row = index.execute("SELECT name,state,unverified FROM records WHERE kind=? AND id=?", (mapped, artifact_id)).fetchone() if mapped else None
            empty["links"].append({"kind": kind, "id": data.text(artifact_id), "basis": basis,
                "name": data.text(row["name"]) if row else "", "state": data.text(row["state"]) if row else "inconnu"})
        parent = empty["group"].get("array_parent") or identifier
        for row in index.execute("SELECT id,name,state FROM records WHERE kind='jobs' AND (id=? OR substr(id,1,?)=?) ORDER BY id LIMIT 100",
                                 (parent, len(parent) + 1, parent + "_")):
            empty["members"].append({"id": row["id"], "name": row["name"], "state": row["state"]})
        if "prepared_submissions" in available:
            for row in connection.execute("SELECT payload,sha256,result,plan_id FROM prepared_submissions ORDER BY created_at DESC LIMIT 1000"):
                if len(row["payload"]) > 1048576 or hashlib.sha256(row["payload"].encode()).hexdigest() != row["sha256"]:
                    continue
                payload, submitted = decode(row["payload"]), decode(row["result"])
                stages = submitted.get("stages") or submitted.get("submitted_stages") or []
                selected = next((stage for stage in stages if isinstance(stage,dict) and stage.get("job_id")==identifier),None)
                if selected is not None:
                    empty["group"]["parent_plan"] = row["plan_id"]
                    empty["group"]["dependencies"] = ", ".join(data.text(item) for item in selected.get("depends_on",[])[:40])
                    empty["members"] = []
                    for stage in stages[:100]:
                        if not isinstance(stage,dict) or not JOB_ID.fullmatch(str(stage.get("job_id",""))): continue
                        job = index.execute("SELECT name,state FROM records WHERE kind='jobs' AND id=?",(stage["job_id"],)).fetchone()
                        empty["members"].append({"id":stage["job_id"],"name":data.text(stage.get("stage")),"state":job["state"] if job else "UNKNOWN"})
                source_job = payload.get("preview",{}).get("resolved",{}).get("source_job_id")
                if submitted.get("job_id")==identifier and isinstance(source_job,str) and JOB_ID.fullmatch(source_job):
                    if len(empty["links"]) < 100 and not any(item["kind"]=="job" and item["id"]==source_job for item in empty["links"]):
                        empty["links"].append({"kind":"job","id":source_job,"name":"Calcul source de la reprise","state":"inconnu","basis":"plan signé"})
                        empty["links_total"] += 1
        return empty
    finally:
        connection.close()


def sessions(path):
    if not path.is_file():
        return []
    connection = connect(path)
    try:
        available = tables(connection)
        if "prepared_submissions" not in available:
            return []
        result = []
        for row in connection.execute("SELECT plan_id,created_at,payload,sha256,state,result FROM prepared_submissions ORDER BY created_at DESC"):
            if len(row["payload"]) > 1048576 or hashlib.sha256(row["payload"].encode()).hexdigest() != row["sha256"]:
                continue
            value, submitted = decode(row["payload"]), decode(row["result"])
            if value.get("kind") not in {"service", "allocation"}:
                continue
            job_id = submitted.get("job_id", "")
            allocation = value["kind"] == "allocation"
            observed = connection.execute("SELECT observed_at,payload,target FROM job_observations WHERE job_id=? ORDER BY observed_at DESC LIMIT 1",
                                          (job_id if allocation else "service:" + row["plan_id"],)).fetchone() if "job_observations" in available else None
            if not observed and not allocation and "job_observations" in available:
                # Versions before 0.5 used the job's key. Only a service-specific
                # payload with both identities may be used as a legacy trace.
                observed = connection.execute("SELECT observed_at,payload,target FROM job_observations WHERE job_id=? ORDER BY observed_at DESC LIMIT 1", (job_id,)).fetchone()
            state = decode(observed["payload"]) if observed else {}
            if state.get("job_id") != job_id or (not allocation and state.get("service_id") != row["plan_id"]):
                state = {}
            service = value.get("preview", {}).get("service", {})
            phase = state.get("state")
            ready = True if (allocation and state.get("ok") is True and phase == "RUNNING") or (not allocation and state.get("current_state_observed") is True and phase == "ready") else None
            expires_at = data.timestamp(state.get("expires_at"))
            if allocation and phase == "RUNNING" and observed:
                from .slurm import parse_sacct_duration
                remaining = parse_sacct_duration(str(state.get("remaining", "")))
                if remaining is not None:
                    expires_at = observed["observed_at"] + remaining
            result.append({"id": row["plan_id"], "name": data.text(service.get("type", value["kind"])),
                "job_id": data.text(job_id), "state": data.text(state.get("state", row["state"])),
                "slurm_state": data.text(phase if allocation else state.get("slurm_state")), "ready": ready,
                "created_at": row["created_at"], "observed_at": observed["observed_at"] if state else None,
                "expires_at": expires_at, "source": source(observed["target"]) if state else "",
                "result_validated": False})
        return result
    finally:
        connection.close()
