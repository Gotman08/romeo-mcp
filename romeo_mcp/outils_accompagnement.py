"""Decouverte des outils et conservation des preuves d'un calcul."""

from typing import Any, Literal

from mcp.server.mcpserver import Context

from .noyau import MUTATING, outil, server
from .reproducibility import export_report


@outil(annotations=MUTATING, description=(
    "Consulte ou change le profil d'outils pour cette connexion : essential ou full. "
    "full reaffiche immediatement les outils avances. Aucun job ni fichier distant n'est modifie."))
async def tool_profile(profile: Literal["essential", "full"] | None = None,
                       ctx: Context | None = None) -> dict[str, Any]:
    if profile is not None and profile not in {"essential", "full"}:
        raise ValueError("Profil inconnu : essential ou full.")
    changed = profile is not None and profile != server.tool_profile
    if profile is not None:
        server.tool_profile = profile
    notified = False
    if changed and ctx is not None:
        try:
            await ctx.session.send_tool_list_changed()
            notified = True
        except Exception:
            # Le choix est applique, meme si le client ne recoit plus les notifications.
            pass
    tools = await server.list_tools()
    return {"ok": True, "profile": server.tool_profile, "tools": [t.name for t in tools],
            "count": len(tools), "changed": changed, "client_notified": notified,
            "scope": "current_stdio_process", "persistent": False,
            "next_step": "Relire tools/list. Pour conserver ce choix au prochain lancement : configure --profile essential ou full."}


@outil(annotations=MUTATING, description=(
    "Exporte hors de Git une fiche JSON/Markdown d'un job soumis via ce MCP : script Slurm filtre, "
    "provenance, ressources mesurees et SHA-256 de fichiers distants explicitement choisis. "
    "Lecture seule sur ROMEO ; cree des fichiers locaux prives. live=false autorise l'export hors ligne."))
def export_job_report(job_id: str, output_dir: str = "", code_dir: str = "",
                      data_files: list[str] | None = None, live: bool = True) -> dict[str, Any]:
    try:
        return export_report(job_id, output_dir=output_dir, code_dir=code_dir, data_files=data_files, live=live)
    except (ValueError, OSError) as exc:
        return {"ok": False, "error": str(exc)}
