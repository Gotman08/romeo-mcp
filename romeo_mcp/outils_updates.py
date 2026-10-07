"""Contrats MCP des mises a jour locales ; aucun acces au cluster."""
from typing import Any

from .noyau import MUTATING, READ_ONLY, outil
from . import update_service


@outil(annotations=READ_ONLY, description="Verifie les releases stables officielles et rend les versions executee/selectionnee, les notes et l'autorisation automatique. Cache 24 h, erreurs 5 min ; refresh=true force GitHub. Ne pas annoncer une absence de mise a jour si ok=false.")
def mcp_update_check(refresh: bool = False) -> dict[str, Any]:
    return update_service.check(refresh)


@outil(annotations=MUTATING, description="Prepare la derniere release officielle dans un processus detache : SHA-256, venv isole, verification et selection atomique. confirm=true apres accord ponctuel ou automatique deja donne ; expected_version lie l'action a la version annoncee. Suivre mcp_update_status avant reconnexion.")
def mcp_update_start(confirm: bool = False, expected_version: str = "") -> dict[str, Any]:
    return update_service.start(confirm, expected_version)


@outil(annotations=READ_ONLY, description="Relit les etapes et le resultat d'une mise a jour apres reconnexion, sans GitHub ni SSH. operation_id vide lit la derniere operation. ready/result_validated signifie version preparee ; running_version prouve celle de ce serveur. Une interruption ne prouve pas une installation.")
def mcp_update_status(operation_id: str = "") -> dict[str, Any]:
    return update_service.status(operation_id)


@outil(annotations=MUTATING, description="Verifie puis selectionne la version precedente en arriere-plan, avec confirm=true. L'automatisme ecarte la version annulee jusqu'a une release plus recente ou une nouvelle autorisation. Suivre mcp_update_status puis reconnecter le MCP.")
def mcp_update_rollback(confirm: bool = False) -> dict[str, Any]:
    return update_service.start(confirm, revert=True)


@outil(annotations=MUTATING, description="Enregistre hors Git l'accord automatique durable ou sa desactivation. automatic=true et confirm=true apres accord de l'utilisateur : les demarrages suivants preparent les releases disponibles sans redemander. ROMEO_AUTO_UPDATE peut imposer la politique. Annoncer les nouvelles versions et suivre leur resultat.")
def mcp_update_policy(automatic: bool, confirm: bool = False) -> dict[str, Any]:
    return update_service.configure(automatic, confirm)
