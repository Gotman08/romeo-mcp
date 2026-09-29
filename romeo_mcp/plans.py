"""Regles de preparation et d'execution des plans exacts, sans interface MCP."""
from dataclasses import asdict
import hashlib
import time
from .cluster import DEFAULT_HOST, require_account
from .guard import check_path
from .pipeline import clause_dependance
from .registry import PLAN_TTL_SECONDS, registry
from .slurm import JobSpec, Plan, plan_job
from .ssh import session
from .execution_backend import (_contexte_chemins, _controle_du_script_genere,
                                _doublon_recent, _error, _soumettre_sbatch)

_SUBMIT_TOOLS = {
    "job": "job_submit", "array": "job_array_submit", "pipeline": "job_pipeline_submit",
    "resilient": "job_resilient_submit", "profile": "job_profile_submit",
    "dataset": "dataset_download", "service": "service_start",
    "python_env": "python_env_create", "python_packages": "python_packages_install",
    "python_wheel": "python_wheel_build", "allocation": "cluster_allocation_start",
    "command": "compute_command_run",
}


def _submission_target(s, home: str, scratch: str) -> dict:
    return {"host": getattr(s, "host", DEFAULT_HOST), "account": require_account(),
            "home": home, "scratch": scratch}


def prepare_submission(kind, s, home, scratch, offline, entries, preview) -> dict:
    """Fige les scripts ; une simulation illustrative ne devient jamais executable."""
    result = {"ok": True, "submitted": False, "mode": "prepared", **preview,
              "submittable": not bool(offline)}
    if offline:
        return {**result, "mode": "simulation", "plan_id": None,
                "next_step": "Reconnecte-toi ou configure ROMEO_SCRATCH, puis prepare un nouveau plan."}
    payload = {"kind": kind, "target": _submission_target(s, home, scratch),
               "entries": entries, "preview": preview}
    identity = registry().prepare_submission(payload)
    return {**result, **identity, "storage": str(registry().path),
            "next_step": "Relis les scripts et avertissements, puis appelle {} avec ce plan_id et confirm=true."
                         .format(_SUBMIT_TOOLS[kind])}


def submit_prepared(kind: str, plan_id: str, confirm: bool) -> dict:
    """Execute une seule fois le contenu conserve, sans regenerer de script."""
    if confirm is not True:
        return _error("La soumission exige confirm=true apres lecture du plan.", submitted=False)
    store = registry()
    try:
        saved = store.prepared_submission(plan_id)
    except ValueError as exc:
        return _error(str(exc), submitted=False)
    if not saved or saved["payload"]["kind"] != kind:
        return _error("Plan introuvable ou incompatible avec cet outil. Prepare un nouveau plan.", submitted=False)
    if saved["state"] != "ready":
        if saved["state"] == "submitted":
            return {**saved["result"], "already_submitted": True}
        return _error("Ce plan a deja fait l'objet d'une tentative de soumission. "
                      "Consulte list_jobs avant de preparer un autre plan.",
                      plan_id=plan_id, state=saved["state"], previous_result=saved["result"])
    if saved["created_at"] <= time.time() - PLAN_TTL_SECONDS:
        return _error("Plan expire (24 h). Prepare un nouveau plan.", submitted=False)
    require_account()
    s = session()
    home, scratch, _, _ = _contexte_chemins(s, True)
    payload = saved["payload"]
    if payload["target"] != _submission_target(s, home, scratch):
        return _error("La cible SSH, le compte ou les racines ont change. Prepare un nouveau plan.", submitted=False)
    plans = []
    for entry in payload["entries"]:
        serialized = entry["plan"]
        plan = Plan(**{**serialized, "spec": JobSpec(**serialized["spec"])})
        problems = _controle_du_script_genere(plan.script)
        if problems:
            return _error("Controle du script : " + " ; ".join(problems), submitted=False)
        plans.append((entry, plan))
    if kind == "job":
        previous = _doublon_recent(plans[0][1].script)
        if previous:
            return _error("Un job identique est deja actif. Consulte job_status.",
                          duplicate_of=previous["job_id"], submitted=False)
    if not store.claim_submission(plan_id):
        return _error("Plan deja reserve par une autre soumission ou expire. Consulte list_jobs.", plan_id=plan_id)

    submitted, identifiers = [], {}
    result = {}
    previous_script = None
    try:
        for entry, plan in plans:
            artifacts = {}
            if "parameters_path" in entry:
                s.write_file(entry["parameters_path"], entry["parameters_text"], mode="400")
                artifacts["parameters"] = {
                    "path": entry["parameters_path"], "source": "generated_content",
                    "sha256": hashlib.sha256(entry["parameters_text"].encode("utf-8")).hexdigest(),
                    "rows": entry["parameter_count"],
                }
            stage = entry.get("stage")
            clause = clause_dependance(stage, identifiers) if stage else ""
            submission = _soumettre_sbatch(
                s, plan, plan.spec.name, options=(clause,) if clause else (),
                ecrire=not entry.get("reuse_previous_script", False),
                script_path=previous_script if entry.get("reuse_previous_script") else entry.get("script_path"), artifacts=artifacts,
                note="plan {} ({})".format(plan_id, kind))
            if not submission["ok"]:
                result = {**submission, "submitted_stages": submitted,
                          "job_ids": list(identifiers.values()),
                          "next_step": "Consulte list_jobs avant une nouvelle preparation ; "
                                       "les etapes deja soumises restent actives."}
                if stage:
                    result["failed_stage"] = stage["name"]
                break
            previous_script = submission["script_path"]
            if stage:
                identifiers[stage["name"]] = submission["job_id"]
                submitted.append({"stage": stage["name"], "job_id": submission["job_id"],
                                  "depends_on": [identifiers[d] for d in stage["depends_on"]]})
                # Une interruption entre deux etapes ne doit pas effacer les
                # identifiants deja obtenus ni permettre de relancer le plan.
                store.update_submission(plan_id, "submitting", {"submitted_stages": submitted})
        else:
            preview = payload["preview"]
            result = {"ok": True, "submitted": True, "warnings": preview["warnings"],
                      "next_step": "Consulte job_status, job_log_tail puis job_efficiency."}
            if kind in {"pipeline", "resilient"}:
                result.update(pipeline=preview.get("pipeline", "resilient"), stages=submitted,
                              job_ids=list(identifiers.values()))
                if "resolved" in preview:
                    result["resolved"] = preview["resolved"]
            else:
                result.update(submission, resolved=preview["resolved"])
                if kind == "service":
                    result["service_id"] = plan_id
                    result["next_step"] = "Consulte service_status(service_id), puis service_connection_info quand pret."
                if kind == "array":
                    result["parameters_file"] = plans[0][0]["parameters_path"]
    except Exception as exc:
        # La tentative reste consommee : apres une coupure reseau, l'absence
        # d'accuse de reception n'est pas une preuve d'absence du job.
        result = _error("Soumission interrompue : {}. Verifie list_jobs avant toute nouvelle tentative."
                        .format(exc), submitted_stages=submitted, job_ids=list(identifiers.values()))
    result.update(plan_id=plan_id, plan_sha256=saved["sha256"])
    store.update_submission(plan_id, "submitted" if result["ok"] else "failed", result)
    return result



def prepare_spec(kind: str, spec: JobSpec, *, details: dict | None = None,
                 connection=None, context: tuple | None = None) -> dict:
    require_account()
    s = connection or session()
    home, scratch, aliases, offline = context if context is not None else _contexte_chemins(s, False)
    if spec.workdir:
        spec.workdir = check_path(spec.workdir, home, scratch, aliases)
    plan = plan_job(spec, scratch)
    details = dict(details or {})
    extra_warnings = details.pop("warnings", [])
    preview = {"script": plan.script, "warnings": plan.warnings + extra_warnings,
               "resolved": {"arch": plan.arch, "partition": plan.partition, "workdir": plan.workdir},
               **(details or {})}
    return prepare_submission(kind, s, home, scratch, offline, [{"plan": asdict(plan)}], preview)


def get_plan(plan_id: str) -> dict:
    saved = registry().prepared_submission(plan_id)
    if saved is None:
        return _error("Plan introuvable.")
    return {"ok": True, "plan_id": plan_id, "plan_sha256": saved["sha256"],
            "created_at": saved["created_at"], "expires_at": saved["created_at"] + PLAN_TTL_SECONDS,
            "expired": saved["created_at"] + PLAN_TTL_SECONDS <= time.time(),
            "state": saved["state"], "result": saved["result"], "plan": saved["payload"],
            "storage": str(registry().path)}
