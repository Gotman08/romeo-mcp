"""Projection publique fermee : aucun texte libre, identifiant local ou hash prive."""
from __future__ import annotations

import hashlib
import json
import re

from .issue_github import marker

DIAGNOSTICS = {
    "unexpected_behavior": "Comportement inattendu",
    "internal_error": "Erreur interne du MCP",
    "invalid_result": "Resultat incoherent ou non verifie",
    "missing_option": "Option documentee absente",
    "timeout": "Delai depasse",
    "connection_failure": "Echec de connexion",
    "incorrect_measurement": "Mesure ou calcul incorrect",
    "slow_operation": "Operation anormalement lente",
    "documentation_mismatch": "Documentation incoherente avec le contrat",
    "display_problem": "Probleme de rendu ou navigation",
}
CATEGORIES = ("bug", "performance", "maintainability", "documentation")
# Catalogue public controle. Le controle docs verifie sa couverture avec tools/list.
PUBLIC_TOOLS = frozenset((
    'audit_orphan_files',
    'cancel_job',
    'checkpoint_export_prepare',
    'checkpoint_export_status',
    'checkpoint_inspect',
    'checkpoint_protect_prepare',
    'checkpoint_protect_submit',
    'cluster_allocation_connection_info',
    'cluster_allocation_prepare',
    'cluster_allocation_start',
    'cluster_gpu_health_run',
    'compute_command_prepare',
    'compute_command_run',
    'dataset_download',
    'dataset_prepare',
    'diagnose_job',
    'download_from_romeo',
    'file_create',
    'file_replace',
    'inject_io_staging',
    'job_array_prepare',
    'job_array_submit',
    'job_checkpoint_request',
    'job_efficiency',
    'job_energy_footprint',
    'job_environment_status',
    'job_link_artifact',
    'job_live_metrics',
    'job_log_search',
    'job_log_tail',
    'job_observation_get',
    'job_pipeline_prepare',
    'job_pipeline_submit',
    'job_prepare',
    'job_profile_prepare',
    'job_profile_submit',
    'job_report_collect',
    'job_report_export',
    'job_report_from_record',
    'job_report_get',
    'job_resilient_prepare',
    'job_resilient_submit',
    'job_resume_prepare',
    'job_resume_status',
    'job_resume_submit',
    'job_stack_trace',
    'job_status',
    'job_submit',
    'job_system_health',
    'list_dir',
    'list_jobs',
    'login_command_run',
    'mcp_diagnostics',
    'mcp_update_check',
    'mcp_update_policy',
    'mcp_update_rollback',
    'mcp_update_start',
    'mcp_update_status',
    'plan_get',
    'profile_report',
    'python_env_create',
    'python_env_prepare',
    'python_packages_install',
    'python_packages_prepare',
    'python_wheel_build',
    'python_wheel_prepare',
    'read_doc',
    'read_remote_file',
    'romeo_capabilities',
    'romeo_fairshare_forecast',
    'romeo_modules',
    'romeo_quota',
    'romeo_selfcheck',
    'romeo_software',
    'romeo_status',
    'sbatch_check_paths',
    'sbatch_validate',
    'search_docs',
    'secret_env_prepare',
    'server',
    'service_connection_info',
    'service_prepare',
    'service_start',
    'service_status',
    'service_stop',
    'storage_usage_audit',
    'suggest_submission_slot',
    'terminal',
    'tool_profile_get',
    'tool_profile_set',
    'transfer_cancel',
    'transfer_prepare',
    'transfer_start',
    'transfer_status',
    'upload_to_romeo',
    'wait_for_job',
))


def version(value) -> str:
    if not isinstance(value, str):
        return "unknown"
    match = re.fullmatch(r"([0-9]{1,2})\.([0-9]{1,2})(?:\.[0-9]{1,3})?(?:(?:a|b|rc|\.dev|\.post)[0-9]{1,3})?", value)
    return ".".join(match.groups()) if match else "unknown"


def projection(document: dict) -> dict:
    name, category = document.get("tool_name"), document.get("category")
    diagnostic = document.get("diagnostic", "unexpected_behavior")
    if name not in PUBLIC_TOOLS or category not in CATEGORIES or diagnostic not in DIAGNOSTICS:
        raise ValueError("Diagnostic technique hors catalogue ; aucune transmission autorisee.")
    context = document.get("context", {})
    return {"schema": 2, "tool_name": name, "category": category, "diagnostic": diagnostic,
            "context": {key: version(context.get(key)) for key in ("romeo_version", "python_version", "mcp_version")}}


def digest(document: dict) -> str:
    return hashlib.sha256(json.dumps(projection(document), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def render(document: dict) -> tuple[str, str]:
    public = projection(document)
    label = DIAGNOSTICS[public["diagnostic"]]
    title = f"[ROMEO MCP/{public['category']}] {public['tool_name']}: {label}"
    context = "\n".join(f"- {key}: `{value}`" for key, value in public["context"].items())
    body = ("Signalement technique genere par un assistant. Diagnostic a verifier par un mainteneur.\n\n"
            f"## Outil\n\n`{public['tool_name']}` — `{public['category']}`\n\n"
            f"## Diagnostic\n\n{label}\n\n## Versions majeures et mineures\n\n{context}\n\n"
            "Le texte libre reste local. Aucune description, reproduction, erreur libre, journal, "
            "chemin, fichier, nom, identifiant de job, configuration SSH ou donnee scientifique n'est transmis.\n\n"
            + marker(digest(document)))
    return title, body
