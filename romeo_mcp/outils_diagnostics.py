"""Local guidance, retained evidence and performance counters; no remote effects."""
from typing import Any, Literal

from .config import setting
from .noyau import READ_ONLY, outil, server
from .observability import TIMINGS
from .profiles import ESSENTIAL_TOOLS, EXPERT_TOOLS
from .registry import registry
from . import ssh
from .outils_contexte import _SPACK_CACHE, _STATUS_CACHE


@outil(annotations=READ_ONLY, description="Durees agregees des outils et du transport SSH, connexions et compteurs de caches. Aucun argument, script ou contenu n'est enregistre.")
def mcp_diagnostics() -> dict[str, Any]:
    transports = {}
    for name, connection in (("short", ssh._SESSION), ("long", ssh._SESSION_LONGUE)):
        if connection is not None:
            transports[name] = {"connections": connection.connections, "timings": connection.timings.snapshot()}
    return {"ok": True, "tools": TIMINGS.snapshot(), "transports": transports,
            "caches": {"spack": _SPACK_CACHE.snapshot(), "cluster_status": _STATUS_CACHE.snapshot()}}


@outil(annotations=READ_ONLY, description="Derniere observation Slurm conservee localement, lisible apres coupure SSH ou redemarrage du MCP. Son age est explicite ; ce n'est pas une nouvelle lecture du cluster.")
def job_observation_get(job_id: str) -> dict[str, Any]:
    observation = registry().observation(str(job_id).strip())
    return {"ok": observation is not None, "observation": observation, "target_checked": False,
            "current_state_observed": False, "next_step": "Utilise job_status pour observer l'etat actuel."}


@outil(annotations=READ_ONLY, description="Outils pertinents pour une tache et leur visibilite dans le profil actuel. Verification locale ; ne certifie ni connexion SSH ni ressources libres.")
def romeo_capabilities(task: Literal["all", "jobs", "resume", "parallel", "services", "python", "files"] = "all") -> dict[str, Any]:
    groups = {
        "jobs": ["job_prepare", "plan_get", "job_submit", "job_status", "job_observation_get", "job_log_tail", "job_efficiency"],
        "resume": ["checkpoint_inspect", "job_checkpoint_request", "job_resilient_prepare", "job_resilient_submit", "job_resume_prepare", "job_resume_submit",
                   "job_resume_status", "checkpoint_protect_prepare", "checkpoint_protect_submit", "checkpoint_export_prepare", "transfer_start", "checkpoint_export_status"],
        "parallel": ["romeo_software", "job_prepare", "job_submit", "job_environment_status", "job_efficiency"],
        "services": ["service_prepare", "service_start", "service_status", "service_connection_info", "service_stop"],
        "python": ["python_env_prepare", "python_env_create", "python_packages_prepare", "python_packages_install", "romeo_software"],
        "files": ["list_dir", "upload_to_romeo", "download_from_romeo", "transfer_prepare", "transfer_start", "transfer_status", "transfer_cancel"],
    }
    if task not in {"all", *groups}:
        raise ValueError("Tache inconnue")
    profile = server.tool_profile
    visible = lambda name: name in ESSENTIAL_TOOLS if profile == "essential" else name not in EXPERT_TOOLS if profile == "full" else True
    return {"ok": True, "profile": profile, "account_configured": bool(setting("ROMEO_ACCOUNT").strip()),
            "ssh_connection_observed": False, "groups": [{"task": key, "tools": [{"name": n, "visible": visible(n)} for n in names]}
                                                          for key, names in groups.items() if task in {"all", key}],
            "next_step": "Utilise romeo_status pour les ressources actuelles ; tool_profile_set permet d'elargir la decouverte."}
