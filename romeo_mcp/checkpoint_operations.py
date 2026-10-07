"""Preparation, observation et export des reprises, independants de l'interface."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import posixpath
import re
import shlex
import time
from pathlib import Path

from . import transfers
from .checkpoint_protocol import atomic_json, digest, read_json, verify_checkpoint
from .cluster import DEFAULT_ACCOUNT
from .execution_backend import _contexte_chemins, _sh
from .guard import check_path
from .plans import prepare_submission
from .registry import registry
from .slurm import JobSpec, plan_job
from .ssh import SSHError, SSHTimeout, session


def source_job(job_id, connection):
    if not re.fullmatch(r"[0-9]+", job_id):
        raise ValueError("job_id doit etre un identifiant Slurm numerique")
    store = registry()
    record = store.get(job_id)
    provenance = store.get_provenance(job_id) if record else None
    saved = (provenance or {}).get("checkpoint_job")
    if not saved:
        raise ValueError("Job sans contrat de reprise/environnement conserve ; preparer un nouveau job avec checkpoint_contract")
    target = {"host": connection.host, "user": connection.user, "account": DEFAULT_ACCOUNT}
    if saved.get("target") != target:
        raise ValueError("La cible SSH ou le compte differe de la soumission originale")
    return record, saved["spec"], target


def runtime_status(job_id):
    connection = session()
    _, spec, target = source_job(job_id, connection)
    contract = spec.get("checkpoint_contract")
    if contract is not None:
        path = posixpath.join(spec["checkpoint_dir"], contract["run_id"], "jobs", job_id + ".json")
    else:
        path = posixpath.join(spec["workdir"], ".romeo-runtime", spec["runtime_id"], job_id + "-mpi.json")
    path = check_path(path, connection.home, connection.scratch, connection.path_aliases)
    key = "checkpoint:" + job_id
    try:
        result = _sh(connection, "head -c 262145 -- %s; romeo_read_rc=$?; printf '\\n'; exit \"$romeo_read_rc\"" % shlex.quote(path),
                     timeout=15, max_chars=262144, read_only=True)
        if not result.ok or result.truncated:
            raise ValueError("Observation de reprise absente ou incomplete ; le job peut etre en attente")
        value = json.loads(result.stdout)
        if not isinstance(value, dict) or value.get("job_id") != job_id:
            raise ValueError("Observation d'un autre job ou malformee")
        if contract and (value.get("run_id") != contract["run_id"] or value.get("world_size") != contract["world_size"]):
            raise ValueError("Observation d'un autre calcul ou d'une autre topologie")
        if not contract and value.get("request_sha256") != digest(spec["mpi_environment"]):
            raise ValueError("Observation d'un autre environnement MPI")
        # L'association complete reste sur ROMEO ; le resultat MCP est compact.
        compact = {k: v for k, v in value.items() if k != "binding"}
        registry().save_observation(key, target, compact)
        return {"ok": True, "job_id": job_id, "runtime_observed": True, "current_process_observed": False,
                "observation_age_seconds": max(0, time.time() - value.get("observed_at", time.time())),
                "source": "persisted_compute_node_evidence", "runtime": compact, "result_validated": False}
    except (SSHError, SSHTimeout, OSError, ValueError) as exc:
        return {"ok": False, "job_id": job_id, "runtime_observed": False, "resume_validated": False,
                "result_validated": False, "error": str(exc), "last_observation": registry().observation(key, target)}


def observe_source_job(connection, job_id):
    from .job_observation import parse_status, status_command
    response = _sh(connection, status_command(job_id), timeout=40, max_chars=10000, read_only=True)
    if not response.ok or response.truncated:
        raise ValueError("Etat Slurm de l'ancien job non observe ; preparation de reprise refusee")
    observed = parse_status(response.stdout, job_id)
    if not observed["ok"] or not observed.get("finished"):
        raise ValueError("L'ancien job doit etre observe comme termine avant preparation d'une reprise/protection")
    return observed


def prepare_from_job(job_id, time_limit="1h", signal_before=300, *, backup_dir=None,
                     quota_fileset=None, quota_group=None, keep_last=3, protect_only=False):
    connection = session()
    record, old, _ = source_job(job_id, connection)
    if old.get("checkpoint_contract") is None:
        raise ValueError("Ce job n'a pas de contrat de checkpoint generique")
    home, scratch, aliases, offline = _contexte_chemins(connection, False)
    observed = observe_source_job(connection, job_id)
    evidence = runtime_status(job_id)
    if not evidence["ok"] or not evidence["runtime"].get("binding_sha256"):
        raise ValueError("Association au programme/donnees du job source non observee ; reprendre apres restauration de l'acces SSH")
    contract = {**old["checkpoint_contract"], "require_resume": True, "action": "protect" if protect_only else "run"}
    contract["expected_binding_sha256"] = evidence["runtime"]["binding_sha256"]
    if backup_dir is not None:
        contract.update(backup_dir=check_path(backup_dir, home, scratch, aliases),
                        quota_fileset=quota_fileset, quota_group=quota_group, keep_last=keep_last)
    if protect_only and not contract.get("backup_dir"):
        raise ValueError("La protection exige backup_dir et quota_fileset")
    spec = JobSpec(**{**old, "time": time_limit, "arch": record["arch"], "runtime_id": "", "array": None,
                      "checkpoint_contract": contract, "signal_before": signal_before,
                      "stage_archive": None, "job_tmpdir": False})
    if protect_only:
        spec.nodes, spec.ntasks_per_node, spec.cpus_per_task = 1, 1, 2
        spec.gpus_per_node, spec.gpus_per_task, spec.gpu_bind = 0, 0, None
        spec.mem_gb = 2
        spec.distributed = "mpi" if spec.mpi_environment is not None else None
    plan = plan_job(spec, scratch)
    if not 0 < signal_before < plan.seconds:
        raise ValueError("signal_before doit etre positif et inferieur au temps alloue")
    kind = "checkpoint_protect" if protect_only else "resume"
    return prepare_submission(kind, connection, home, scratch, offline, [{"plan": asdict(plan)}],
                              {"script": plan.script, "warnings": plan.warnings + [
                                  "Une reprise est validee seulement apres les preuves de chargement et progression de tous les rangs.",
                                  "Une copie sur ROMEO protege la retention ; exporter vers la machine du client pour une copie independante."],
                               "resolved": {"source_job_id": job_id, "source_state": observed["state"], "arch": plan.arch,
                                            "workdir": plan.workdir, "checkpoint_dir": spec.checkpoint_dir, "checkpoint_contract": contract}})


METADATA_READER = '''import hashlib,json,os,re,sys
from pathlib import Path
root=Path(sys.argv[1]); rows=[]
if root.exists():
 for folder in root.iterdir():
  if not re.fullmatch(r"generation-[0-9]{20}",folder.name): continue
  if len(rows)>=1000: raise ValueError("Trop de generations")
  row={"generation":int(folder.name[11:]),"directory":str(folder),"integrity_verified":False}
  try:
   p=folder/"manifest.json"
   if folder.is_symlink() or p.is_symlink(): raise ValueError("Lien symbolique")
   with p.open("rb") as f: data=f.read(1048577)
   if len(data)>1048576: raise ValueError("Manifeste trop volumineux")
   m=json.loads(data)
   row.update(declared_complete=m.get("complete") is True,schema=m.get("schema"),step=m.get("step"),
              world_size=m.get("world_size"),binding_sha256=m.get("binding_sha256"),manifest_sha256=hashlib.sha256(data).hexdigest())
  except (OSError,ValueError,AttributeError) as e: row["error"]=str(e)[:200]
  rows.append(row)
rows.sort(key=lambda r:r["generation"],reverse=True)
print(json.dumps({"generations":rows[:20],"count":len(rows),"truncated":len(rows)>20,"integrity_verified":False}))
'''


def inspect_checkpoints(job_id):
    connection = session()
    _, spec, _ = source_job(job_id, connection)
    contract = spec.get("checkpoint_contract")
    if contract is None:
        raise ValueError("Ce job n'a pas de contrat de checkpoint")
    path = check_path(posixpath.join(spec["checkpoint_dir"], contract["run_id"]),
                      connection.home, connection.scratch, connection.path_aliases)
    response = _sh(connection, "python3 -c %s %s" % (shlex.quote(METADATA_READER), shlex.quote(path)),
                   timeout=20, max_chars=20000, read_only=True)
    if not response.ok or response.truncated:
        raise ValueError("Inspection des manifestes absente ou incomplete")
    metadata = json.loads(response.stdout)
    return {"ok": True, "job_id": job_id, "run_id": contract["run_id"], "observed_at": time.time(), **metadata,
            "next_step": "job_resume_prepare puis job_resume_submit : le noeud verifiera les fichiers et observera la reprise."}


def request_checkpoint(job_id):
    connection = session()
    _, spec, _ = source_job(job_id, connection)
    if spec.get("checkpoint_contract") is None:
        raise ValueError("Une demande verifiable exige checkpoint_contract")
    from .job_observation import parse_status, status_command
    observed = _sh(connection, status_command(job_id), timeout=40, max_chars=10000, read_only=True)
    state = parse_status(observed.stdout, job_id) if observed.ok and not observed.truncated else {}
    if not state.get("ok") or state.get("state") != "RUNNING":
        raise ValueError("Le job doit etre observe RUNNING avant demande de sauvegarde")
    runtime = runtime_status(job_id)
    if not runtime["ok"] or runtime["runtime"].get("state") not in {"running", "awaiting_resume"}:
        raise ValueError("Supervision applicative active non observee")
    current = runtime["runtime"]
    if current.get("signal_requested") and not current.get("checkpoint_after_signal_verified"):
        return {"ok": True, "job_id": job_id, "signal_requested": False, "already_requested": True,
                "checkpoint_verified": False, "next_step": "Attendre la preuve de sauvegarde avec job_resume_status."}
    try:
        response = _sh(connection, "scancel --batch --signal=USR1 " + job_id, timeout=20, max_chars=1000)
    except (SSHError, SSHTimeout) as exc:
        return {"ok": False, "job_id": job_id, "request_outcome": "unknown", "error": str(exc), "checkpoint_verified": False}
    return {"ok": response.ok and not response.truncated, "job_id": job_id, "signal_requested": response.ok,
            "checkpoint_verified": False, "application_acknowledged": False,
            "next_step": "Lire job_resume_status et attendre checkpoint_after_signal_verified=true avant d'arreter le calcul."}


def export_prepare(job_id, local_path):
    observation = runtime_status(job_id)
    if not observation["ok"]:
        raise ValueError("Une observation de checkpoint verifie est requise avant export")
    runtime = observation["runtime"]
    checkpoint = runtime.get("latest_checkpoint") or runtime.get("checkpoint")
    if not checkpoint or checkpoint.get("integrity_verified") is not True:
        raise ValueError("Aucun checkpoint verifie a exporter")
    local = Path(local_path).expanduser().absolute() / checkpoint["run_id"] / ("generation-%020d" % checkpoint["generation"])
    if local.exists():
        raise ValueError("La destination d'export doit etre nouvelle pour conserver les copies precedentes")
    # Le noeud a deja verifie la source. Apres SCP, la machine du client verifie
    # le manifeste fige et chaque fichier ; pas de gros hachage sur le login.
    transfer = transfers.prepare("download", str(local), checkpoint["directory"], recursive=True, verify=False)
    record = {"transfer_id": transfer["transfer_id"], "transfer_sha256": transfer["plan"]["sha256"],
              "job_id": job_id, "checkpoint": checkpoint, "local_path": transfer["plan"]["local_path"],
              "max_bytes": max(checkpoint["bytes"], 1), "created_at": time.time()}
    record["sha256"] = digest(record)
    atomic_json(registry().path.parent / "checkpoint-exports" / (record["transfer_id"] + ".json"), record, immutable=True)
    return {**transfer, "checkpoint": checkpoint, "independent_backup": False,
            "next_step": "transfer_start(transfer_id, confirm=true), puis checkpoint_export_status pour valider la copie locale."}


def export_status(transfer_id, refresh=False):
    _, plan = transfers.load(transfer_id)
    path = registry().path.parent / "checkpoint-exports" / (transfer_id + ".json")
    record = read_json(path)
    signed = {k: v for k, v in record.items() if k != "sha256"}
    if record.get("sha256") != digest(signed) or record.get("transfer_sha256") != plan["sha256"]:
        raise ValueError("Plan d'export de checkpoint altere")
    result = transfers.status(transfer_id, 0)
    result.update(independent_backup=False, checkpoint_integrity_verified=False)
    verified_path = path.with_suffix(".verified.json")
    if result["state"] not in {"completed", "completed_unverified"}:
        return result
    if verified_path.exists() and not refresh:
        saved = read_json(verified_path)
        if saved.get("export_sha256") != record["sha256"]:
            raise ValueError("Preuve d'export d'un autre plan")
        return {**result, **saved, "current_integrity_observed": False,
                "verification_age_seconds": max(0, time.time() - saved["verified_at"])}
    try:
        expected = record["checkpoint"]
        verified = verify_checkpoint(Path(record["local_path"]) / "manifest.json", run_id=expected["run_id"],
                                     world_size=expected["world_size"], max_bytes=record["max_bytes"], deadline=time.monotonic() + 900)
        if verified["manifest_sha256"] != expected["manifest_sha256"]:
            raise ValueError("Copie d'un autre checkpoint que celui prepare")
    except (OSError, ValueError) as exc:
        return {**result, "ok": False, "error": str(exc), "result_validated": False}
    saved = {"checkpoint_integrity_verified": True, "independent_backup": True, "result_validated": True,
             "export_sha256": record["sha256"], "manifest_sha256": verified["manifest_sha256"], "verified_at": time.time(),
             "independence_basis": "Copie sur la machine du client MCP, hors de la cible SSH ROMEO"}
    atomic_json(verified_path, saved)
    return {**result, **saved, "current_integrity_observed": True, "verification_age_seconds": 0}
