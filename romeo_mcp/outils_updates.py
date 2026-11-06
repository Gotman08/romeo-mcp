"""Lecture de l'etat des mises a jour ; leur installation reste hors du MCP."""
from typing import Any

from .noyau import READ_ONLY, outil
from . import update_service


@outil(annotations=READ_ONLY, description="Verifie les releases stables officielles et rend les versions executee/selectionnee, les notes et l'accord automatique. Cache 24 h, erreurs 5 min ; refresh=true force GitHub. Ne pas annoncer une absence de mise a jour si ok=false. N'installe rien : l'utilisateur lance python -m romeo_mcp update dans son terminal.")
def mcp_update_check(refresh: bool = False) -> dict[str, Any]:
    return update_service.check(refresh)


@outil(annotations=READ_ONLY, description="Relit les etapes et le resultat d'une mise a jour apres reconnexion, sans GitHub ni SSH. operation_id vide lit la derniere operation. ready/result_validated signifie version preparee ; running_version prouve celle de ce serveur. Une interruption ne prouve pas une installation.")
def mcp_update_status(operation_id: str = "") -> dict[str, Any]:
    return update_service.status(operation_id)
