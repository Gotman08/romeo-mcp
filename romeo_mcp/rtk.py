"""RTK explicite pour les commandes utilisateur, jamais pour les sondes internes."""
from __future__ import annotations

import posixpath
import shlex
import time

from .guard import GuardError
from .ssh import SSHError, SSHTimeout


class Deadline:
    """Un seul delai partage par detection, reecriture et commande."""

    def __init__(self, seconds: int):
        self.end = time.monotonic() + seconds

    def remaining(self) -> float:
        remaining = self.end - time.monotonic()
        if remaining <= 0:
            raise SSHTimeout("Delai de la commande depasse ; aucune nouvelle execution lancee.")
        return remaining


def find_binary(connection, run, deadline: Deadline, cwd: str | None = None) -> str | None:
    """La session persistante peut avoir un PATH anterieur a l'installation."""
    candidate = shlex.quote(posixpath.join(connection.home, ".local/bin/rtk"))
    probe = ("if test -x {0}; then printf '%s\\n' {0}; "
             "elif type -P rtk; then :; else exit 127; fi").format(candidate)
    result = run(connection, probe, timeout=deadline.remaining(), cwd=cwd, max_chars=4096)
    if result.rc == 127 and not result.stdout.strip():
        return None
    result.check("localisation de RTK")
    path = result.stdout.strip()
    if result.truncated or not path.startswith("/") or any(c in path for c in "\r\n\x00"):
        raise SSHError("La localisation de RTK ne fournit pas un chemin absolu complet.")
    return path


def rewrite_command(connection, command: str, run, deadline: Deadline,
                    cwd: str | None = None) -> tuple[str, dict]:
    binary = find_binary(connection, run, deadline, cwd)
    metadata = {"requested": True, "available": binary is not None, "applied": False,
                "path": binary, "reason": "not_installed"}
    if binary is None:
        return command, metadata
    result = run(connection, "RTK_TELEMETRY_DISABLED=1 {} rewrite -- {}".format(
        shlex.quote(binary), shlex.quote(command)), timeout=deadline.remaining(),
        cwd=cwd, max_chars=8000)
    # 3 est aussi une reecriture : l'approbation appartient au client MCP.
    # Ne jamais relancer une commande utilisateur pour recuperer sa sortie brute.
    if result.rc == 2:
        raise GuardError("RTK a refuse la commande ; aucune execution lancee.")
    if result.rc == 1 and not result.stdout.strip():
        return command, {**metadata, "reason": "not_rewritten"}
    if result.rc not in {0, 3} or result.truncated or not result.stdout.strip():
        raise SSHError("Reecriture RTK incomplete ou en echec ; aucune execution lancee.")
    rewritten = result.stdout.strip()
    applied = rewritten != command
    return rewritten, {**metadata, "applied": applied,
                       "reason": "rewritten" if applied else "already_wrapped"}


def with_environment(command: str, binary: str) -> str:
    """Le lanceur utilisateur choisit lui-meme le binaire de l'architecture."""
    return 'export PATH={}:"$PATH"\nexport RTK_TELEMETRY_DISABLED=1\n{}'.format(
        shlex.quote(posixpath.dirname(binary)), command)
