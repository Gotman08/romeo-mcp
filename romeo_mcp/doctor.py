"""Diagnostic borne, uniquement compose de lectures SSH et Slurm."""

from __future__ import annotations

from datetime import datetime, timezone
import re
import shlex

from .cluster import require_account
from .config import setting
from .ssh import RomeoSession, SSHError, SSHTimeout


def quota_rows(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        # GPFS separe les colonnes de volume et de fichiers par un trait vertical.
        fields = [field for field in line.split() if field != "|"]
        if len(fields) >= 8 and fields[0] == "gpfs":
            row = dict(zip(
                ("filesystem", "fileset", "type", "used", "soft", "hard", "in_doubt", "grace"),
                fields[:8]))
            if len(fields) >= 13:
                row.update(zip(("files_used", "files_soft", "files_hard", "files_in_doubt", "files_grace"), fields[8:13]))
            rows.append(row)
    return rows


def ssh_failure(exc: Exception) -> tuple[str, str]:
    message = str(exc).lower()
    if isinstance(exc, SSHTimeout):
        return "ssh_timeout", "Connexion trop lente : verifier le reseau, le VPN et l'alias SSH."
    if "permission denied" in message or "publickey" in message:
        return "ssh_authentication", "Authentification refusee : verifier la cle enregistree et l'agent SSH."
    if "host key" in message or "identification has changed" in message:
        return "ssh_host_key", "Empreinte SSH non validee : verifier l'hote selon la documentation ROMEO."
    if "introuvable dans le path" in message:
        return "ssh_missing", "Installer OpenSSH et rendre la commande ssh disponible dans le PATH."
    return "ssh_connection", "Connexion impossible : tester ssh avec le meme alias, compte local et agent."


def live_checks(*, timeout: int = 20, project_group: str = "", session_factory=RomeoSession) -> dict:
    account = setting("ROMEO_ACCOUNT").strip()
    require_account(account)
    group = project_group or account
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", group):
        raise ValueError("Le groupe de stockage doit etre un identifiant simple.")
    timeout = max(2, min(int(timeout), 60))
    checks = []

    def add(name, status, code, message, **facts):
        checks.append({"check": name, "status": status, "code": code,
                       "message": message, **facts})

    def query(name, command):
        try:
            result = connection.run(command, timeout=timeout, max_chars=16000)
        except (SSHError, SSHTimeout) as exc:
            code, advice = ssh_failure(exc)
            add(name, "error", code, advice)
            return None
        if result.rc != 0 or result.truncated:
            code = "command_missing" if result.rc == 127 else "query_failed"
            if result.truncated:
                code = "incomplete_output"
            add(name, "error", code,
                "Lecture impossible ou incomplete. Verifier les droits et la disponibilite de la commande.",
                return_code=result.rc)
            return None
        return result.stdout

    connection = session_factory(host=setting("ROMEO_HOST", "romeo1"))
    try:
        identity = query("ssh", "id -un")
        if identity is None or not re.fullmatch(r"[A-Za-z0-9_.-]+", identity.strip()):
            if identity is not None:
                add("ssh", "error", "invalid_identity", "SSH repond mais l'identite distante est illisible.")
            for name in ("slurm_project", "partitions", "quota_user", "quota_project"):
                add(name, "skipped", "ssh_unavailable", "Verifier d'abord la connexion SSH.")
        else:
            add("ssh", "ok", "connected", "Connexion SSH et identite distante verifiees.")
            assoc = query("slurm_project",
                'sacctmgr -nP show assoc where user="$(id -un)" account={} '
                'format=Account,Partition,QOS,DefaultQOS'.format(shlex.quote(account)))
            if assoc is not None:
                entries = [line.split("|") for line in assoc.splitlines()]
                matching = [entry for entry in entries if entry and entry[0].strip() == account]
                add("slurm_project", "ok" if matching else "error",
                    "association_found" if matching else "association_missing",
                    "Association Slurm du projet trouvee." if matching else
                    "Aucune association pour ce projet. Verifier configure --account ou contacter ROMEO.",
                    associations=len(matching))

            partitions = query("partitions", "sinfo -h -o '%P|%a|%l|%D'")
            if partitions is not None:
                rows = []
                for line in partitions.splitlines():
                    parts = line.strip().split("|")
                    if len(parts) == 4 and parts[3].isdigit():
                        rows.append({"name": parts[0].rstrip("*"), "availability": parts[1],
                                     "time_limit": parts[2], "nodes": int(parts[3])})
                usable = any(r["availability"].lower() == "up" and r["nodes"] > 0 for r in rows)
                add("partitions", "ok" if usable else "error",
                    "partitions_visible" if usable else "no_available_partition",
                    "Partitions visibles ; leurs ACL et la QOS restent applicables a chaque job." if usable else
                    "Aucune partition ouverte lisible. Verifier sinfo et les annonces de maintenance.",
                    partitions=rows)

            for name, selector in (("quota_user", '-u "$(id -un)"'),
                                   ("quota_project", "-g " + shlex.quote(group))):
                text = query(name, "mmlsquota --block-size auto {} gpfs".format(selector))
                if text is None:
                    if name == "quota_project":
                        checks[-1]["message"] += " Le groupe GPFS peut differer du projet Slurm : utiliser --project-group."
                    continue
                rows = quota_rows(text)
                exceeded = any(r.get(key, "none").lower() not in {"none", "-", ""}
                               for r in rows for key in ("grace", "files_grace"))
                add(name, "warning" if exceeded else "ok" if rows else "error",
                    "quota_grace" if exceeded else "quota_read" if rows else "quota_unreadable",
                    "Un quota souple est depasse : verifier la grace et l'espace libre." if exceeded else
                    "Quotas lus." if rows else "Aucune ligne GPFS lisible. Verifier le groupe de stockage et les droits.",
                    quotas=rows)
    finally:
        connection.close()
    return {"ok": all(c["status"] == "ok" for c in checks), "ssh_checked": True,
            "read_only": True, "checked_at": datetime.now(timezone.utc).isoformat(),
            "timeout_per_check_seconds": timeout, "checks": checks}
