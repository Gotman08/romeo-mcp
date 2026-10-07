"""MCP contracts for background file transfers."""
from typing import Any, Literal
from .noyau import MUTATING, READ_ONLY, outil
from . import transfers


@outil(annotations=MUTATING, description="Prepare un transfert upload/download dans un plan local immuable. Aucun fichier distant n'est copie ; relis le plan avant transfer_start.")
def transfer_prepare(direction: Literal["upload", "download"], local_path: str, remote_path: str,
                     recursive: bool = False, verify: bool = True) -> dict[str, Any]:
    return transfers.prepare(direction, local_path, remote_path, recursive, verify)


@outil(annotations=MUTATING, description="Consomme un plan une seule fois et demarre son transfert dans un processus detache. Le MCP reste disponible ; la fin et l'integrite se lisent avec transfer_status.")
def transfer_start(transfer_id: str, confirm: bool = False) -> dict[str, Any]:
    return transfers.start(transfer_id, confirm)


@outil(annotations=READ_ONLY, description="Relit la progression et les journaux bornes d'un transfert apres reconnexion. Heartbeat ancien signifie activite non verifiee ; completed_unverified ne certifie pas l'integrite.")
def transfer_status(transfer_id: str, max_chars: int = 4000) -> dict[str, Any]:
    return transfers.status(transfer_id, max_chars)


@outil(annotations=MUTATING, description="Demande l'annulation du transfert detache. L'acceptation de la demande ne prouve pas l'arret. Des fichiers partiels peuvent rester ; ils ne sont pas supprimes automatiquement.")
def transfer_cancel(transfer_id: str, confirm: bool = False) -> dict[str, Any]:
    return transfers.cancel(transfer_id, confirm)
