"""Projection for JSON exports, matching the native viewer's sharing mode."""
from copy import deepcopy


def project(snapshot):
    value = deepcopy(snapshot)
    for job in value.get("jobs", []) + value.get("recent_jobs", []):
        job.update(name="[nom masqué]", partition="[masquée]")
    for transfer in value.get("transfers", []):
        transfer.update(name="[fichier masqué]", local_path="[chemin masqué]", remote_path="[chemin masqué]")
    for report in value.get("reports", {}).get("items", []):
        report.update(summary="[résumé masqué]", issue_url="")
    for alert in value.get("attention", []): alert["name"] = "[nom masqué]"
    dossier = value.get("workspace", {})
    for link in dossier.get("links", []): link["name"] = "[nom masqué]"
    for member in dossier.get("members", []): member["name"] = "[nom masqué]"
    if dossier.get("logs"): dossier["logs"]["content"] = "[journal masqué]"
    value["warnings"] = ["Avertissement de lecture · contenu masqué" for _ in value.get("warnings", [])]
    return value
