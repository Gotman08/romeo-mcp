"""Outils de rapport public : l'accord initial persiste, les donnees sont filtrees."""
from typing import Any, Literal

from mcp.types import ToolAnnotations

from . import issue_reports
from .noyau import MUTATING, READ_ONLY, outil

PUBLICATION = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=True)
REPORT = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=True)


@outil(annotations=READ_ONLY, description="Lit l'autorisation persistante des rapports publics, la methode GitHub configuree (non verifiee) et les limites. Aucun reseau, SSH, lecture de journaux ou collecte en arriere-plan. L'envoi automatique est desactive par defaut.")
def mcp_issue_policy_get() -> dict[str, Any]:
    return issue_reports.policy_get()


@outil(annotations=MUTATING, description="Active une fois les rapports GitHub automatiques avec automatic=true, confirm=true apres accord explicite de l'utilisateur. Cet accord persiste hors Git : ne pas le redemander pour chaque incident. automatic=false desactive les futurs envois automatiques. Les rapports sont publics dans Gotman08/romeo-mcp.")
def mcp_issue_policy_set(automatic: bool, confirm: bool = False) -> dict[str, Any]:
    return issue_reports.policy_set(automatic, confirm)


@outil(annotations=REPORT, description="Signale un defaut observe du MCP ROMEO. diagnostic choisit un libelle technique controle : seules categorie, nom d'outil et versions majeures/mineures sont transmis sur GitHub. Resume, observation, attendu, reproduction et erreur libre restent filtres et locaux ; ne pas y mettre de donnees personnelles. Publication avec accord persistant seulement, recherche des doublons et relecture verifiee. Ne pas signaler les outils mcp_issue_* ou un simple echec du programme utilisateur.")
def mcp_issue_report(tool_name: str, summary: str, observed: str, expected: str,
                     steps: list[str] | None = None,
                     category: Literal["bug", "performance", "maintainability", "documentation"] = "bug",
                     error_code: str = "",
                     diagnostic: Literal["unexpected_behavior", "internal_error", "invalid_result", "missing_option",
                                         "timeout", "connection_failure", "incorrect_measurement", "slow_operation",
                                         "documentation_mismatch", "display_problem"] = "unexpected_behavior") -> dict[str, Any]:
    from . import server as assembled
    candidate = getattr(assembled, tool_name, None)
    if tool_name not in ("server", "terminal") and not (callable(candidate) and hasattr(candidate, "__wrapped__")):
        raise ValueError("Outil ROMEO inconnu ; utiliser le nom annonce dans tools/list, server ou terminal.")
    return issue_reports.report(tool_name, summary, observed, expected, steps, category, error_code, diagnostic)


@outil(annotations=PUBLICATION, description="Publie ou reconcilie un rapport local filtre. confirm=true apres accord ponctuel, ou accord automatique deja enregistre. Relit GitHub avant toute creation, ne reposte jamais un envoi incertain et verifie l'issue apres creation. Aucun envoi n'est valide sur la seule intention ou sur une erreur reseau.")
def mcp_issue_publish(report_id: str, confirm: bool = False) -> dict[str, Any]:
    return issue_reports.publish(report_id, confirm)


@outil(annotations=READ_ONLY, description="Relit un rapport par report_id ou les vingt derniers rapports, sans GitHub ni SSH. result_validated=true correspond a une issue observee ; publishing est une intention persistante qui peut avoir ete interrompue. mcp_issue_publish reconcilie un resultat incertain sans double creation.")
def mcp_issue_status(report_id: str = "") -> dict[str, Any]:
    return issue_reports.status(report_id)
