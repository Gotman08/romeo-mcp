"""Decouverte des outils et conservation des preuves d'un calcul."""

from typing import Any, Literal

from mcp.server.mcpserver import Context

from .noyau import MUTATING, READ_ONLY, outil, server
from .reproducibility import collect_report, export_snapshot, report_get


@outil(annotations=READ_ONLY, description=(
    "Consulte le profil et le catalogue d'outils de cette connexion, sans les modifier."))
async def tool_profile_get() -> dict[str, Any]:
    tools = await server.list_tools()
    return {"ok": True, "profile": server.tool_profile, "tools": [t.name for t in tools],
            "count": len(tools), "scope": "current_stdio_process", "persistent": False}


@outil(annotations=MUTATING, description=(
    "Change le profil d'outils pour cette connexion : essential, full ou expert. "
    "full affiche les outils metier, expert ajoute les executeurs de shell arbitraire. Aucun job ni fichier distant n'est modifie."))
async def tool_profile_set(profile: Literal["essential", "full", "expert"],
                           ctx: Context | None = None) -> dict[str, Any]:
    if profile not in {"essential", "full", "expert"}:
        raise ValueError("Profil inconnu : essential, full ou expert.")
    changed = profile != server.tool_profile
    server.tool_profile = profile
    notified = False
    if changed and ctx is not None:
        try:
            await ctx.session.send_tool_list_changed()
            notified = True
        except Exception:
            # Le choix est applique, meme si le client ne recoit plus les notifications.
            pass
    return {**await tool_profile_get(), "changed": changed, "client_notified": notified,
            "next_step": "Relire tools/list. Pour conserver ce choix au prochain lancement : configure --profile essential, full ou expert."}


@outil(annotations=MUTATING, description=(
    "Collecte un releve date du job : observations SSH, comptabilite Slurm et empreintes des fichiers choisis. "
    "Enregistre un releve local immuable et rend report_id. Ne cree aucun fichier d'export et ne modifie pas ROMEO."))
def job_report_collect(job_id: str, code_dir: str = "", data_files: list[str] | None = None) -> dict[str, Any]:
    return collect_report(job_id, code_dir=code_dir, data_files=data_files)


@outil(annotations=MUTATING, description="Cree un releve immuable a partir du registre local uniquement. Aucun acces SSH ; les observations distantes manquantes sont indiquees.")
def job_report_from_record(job_id: str) -> dict[str, Any]:
    return collect_report(job_id, live=False)


@outil(annotations=READ_ONLY, description="Relit exactement un releve conserve, son horodatage et son empreinte. Aucun acces SSH ni nouvelle collecte.")
def job_report_get(report_id: str) -> dict[str, Any]:
    return report_get(report_id)


@outil(annotations=MUTATING, description="Exporte exactement le releve report_id en JSON, Markdown et script filtre. Cree des fichiers locaux prives hors de Git, sans SSH ni collecte supplementaire.")
def job_report_export(report_id: str, output_dir: str = "") -> dict[str, Any]:
    return export_snapshot(report_id, output_dir=output_dir)
