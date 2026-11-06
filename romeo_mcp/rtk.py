"""RTK pour les commandes utilisateur, jamais pour les sondes internes.

Au premier besoin, le MCP pose la release epinglee dans ~/.local/bin du compte : une
tentative par compte et par processus, rien au demarrage du serveur et jamais par-dessus
un fichier existant. ROMEO_RTK_AUTO_INSTALL=0 desactive ce comportement.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
import posixpath
import re
import shlex
import threading
import time

from .execution_backend import _sh
from .guard import GuardError
from .resource_locks import ResourceBusy, ResourceLease
from .ssh import SSHError, SSHTimeout, session


class Deadline:
    """Un seul delai partage par detection, reecriture et commande."""

    def __init__(self, seconds: int):
        self.end = time.monotonic() + seconds

    def remaining(self) -> float:
        remaining = self.end - time.monotonic()
        if remaining <= 0:
            raise SSHTimeout("Delai de la commande depasse ; aucune nouvelle execution lancee.")
        return remaining

    def extend(self, seconds: float) -> None:
        """L'installation au premier besoin ne prend rien sur le delai de la commande."""
        self.end += seconds


@dataclass(frozen=True)
class Release:
    """Archive officielle attendue ; ses empreintes sont verifiees sur le login."""
    version: str
    asset: str
    archive_sha256: str
    archive_size: int
    binary_sha256: str

    @property
    def url(self) -> str:
        return "https://github.com/rtk-ai/rtk/releases/download/v{}/{}".format(self.version, self.asset)


#: Edition Apache-2.0 et binaire statique. Choix, verifications et renouvellement :
#: docs/rtk.md, section « Release épinglée ».
PINNED = Release(
    version="1.1.0",
    asset="rtk-oss-x86_64-unknown-linux-musl.tar.gz",
    archive_sha256="4dec94a64035e08189ae82fd5408fe4ae9ae27a665fc07e3e3ec3c4c2d8e8a3e",
    archive_size=5834617,
    binary_sha256="0b80810970ce2c79c92deaa474bbcf6f1cf01ac93baab0e273ee6cb4ef950d10",
)
_INSTALL_DIRECTORY = ".local/bin"
_INSTALL_TIMEOUT = 45

#: Tout se joue dans un dossier temporaire du home, sur le meme systeme de fichiers que
#: la cible : un echec avant la bascule ne laisse rien, et `ln` refuse d'ecraser.
_INSTALL = r'''
set -u
umask 077
export LC_ALL=C RTK_TELEMETRY_DISABLED=1
fail() { printf 'RTK_INSTALL_FAILED %s\n' "$2"; exit "$1"; }
[ "$(uname -s)/$(uname -m)" = Linux/x86_64 ] || fail 10 "$(uname -sm)"
physical_home=$(readlink -f -- "$home" 2>/dev/null)
[ -n "$physical_home" ] && [ "$physical_home" != / ] || fail 11 home
directory=$(readlink -m -- "$home/.local/bin" 2>/dev/null)
case "$directory/" in "$physical_home"/*) ;; *) fail 11 "$directory" ;; esac
target=$directory/rtk
if [ -e "$target" ] || [ -L "$target" ]; then fail 12 present; fi
for tool in curl sha256sum tar mktemp timeout; do
    type -P "$tool" >/dev/null || fail 18 "$tool"
done
anchor=$directory
while [ ! -e "$anchor" ] && [ ! -L "$anchor" ]; do anchor=$(dirname -- "$anchor"); done
[ -d "$anchor" ] && [ -w "$anchor" ] || fail 16 "$anchor"
tmp=$(mktemp -d -- "$anchor/.rtk-install.XXXXXX") || fail 16 mktemp
trap 'rm -f -- "$tmp/archive" "$tmp/rtk"; rmdir -- "$tmp"' EXIT
trap 'exit 129' HUP INT TERM
curl -q --proto '=https' --proto-redir '=https' --tlsv1.2 -fsSL --connect-timeout 10 --max-time 30 \
    --max-filesize "$archive_size" -o "$tmp/archive" "$url"
actual=$?
# Code 63 de curl : l'archive annoncee depasse la taille epinglee.
[ "$actual" != 63 ] || fail 14 "size > $archive_size"
[ "$actual" = 0 ] || fail 13 "curl $actual"
actual=$(stat -c %s -- "$tmp/archive")
[ "$actual" = "$archive_size" ] || fail 14 "size $actual"
actual=$(sha256sum <"$tmp/archive" | cut -d' ' -f1)
[ "$actual" = "$archive_sha256" ] || fail 14 "sha256 $actual"
tar -xzOf "$tmp/archive" rtk >"$tmp/rtk" || fail 15 tar
actual=$(sha256sum <"$tmp/rtk" | cut -d' ' -f1)
[ "$actual" = "$binary_sha256" ] || fail 15 "sha256 $actual"
chmod 755 -- "$tmp/rtk" || fail 16 chmod
actual=$(timeout 5 "$tmp/rtk" --version 2>&1)
[ "$actual" = "rtk $version" ] || fail 15 version
mkdir -p -- "$directory" || fail 16 mkdir
if ! ln -T -- "$tmp/rtk" "$target"; then
    if [ -e "$target" ] || [ -L "$target" ]; then fail 12 present; fi
    fail 16 ln
fi
actual=$(timeout 5 "$target" --version 2>&1)
[ "$actual" = "rtk $version" ] || fail 17 version
printf 'RTK_INSTALL_DONE\n'
'''

_FAILURES = {
    10: "Le login n'est pas en Linux x86_64",
    11: "~/.local/bin sort du home apres resolution des liens",
    12: "Un fichier occupe deja ~/.local/bin/rtk et n'est pas remplace",
    13: "Telechargement impossible depuis le login",
    14: "L'archive telechargee differe de l'epingle (taille ou SHA-256)",
    15: "Extraction impossible ou binaire different de l'epingle",
    16: "Ecriture impossible dans le home",
    18: "Outil absent du login",
}
_RETRY = "RTK reste absent pour ce processus MCP ; nouvel essai au prochain demarrage du serveur."

_attempts: dict[tuple[str, str], dict] = {}
_attempts_lock = threading.Lock()


def auto_install_enabled() -> bool:
    return os.environ.get("ROMEO_RTK_AUTO_INSTALL", "1").casefold() not in {"0", "false", "no"}


def install_script(home: str, release: Release = PINNED) -> str:
    """Script execute sur le login ; toutes les valeurs sont citees."""
    values = dict(home=home, url=release.url, version=release.version, archive_sha256=release.archive_sha256,
                  archive_size=str(release.archive_size), binary_sha256=release.binary_sha256)
    return "".join("{}={}\n".format(key, shlex.quote(value)) for key, value in values.items()) + _INSTALL


def attempt(connection, release: Release = PINNED) -> dict:
    """Une seule execution du script ; une cause distante devient un etat, pas une exception."""
    identity = "{}\0{}".format(connection.host, connection.user)
    lease = "action:rtk-install:" + hashlib.sha256(identity.encode()).hexdigest()
    try:
        with ResourceLease([(lease, True)]):
            # La seconde session garde le transport commun libre pendant le telechargement.
            remote = _sh(session(longue=True), install_script(connection.home, release),
                         timeout=_INSTALL_TIMEOUT, max_chars=4000)
    except ResourceBusy:
        return {"state": "in_progress", "message": "Un autre processus MCP installe RTK sur ce compte."}
    except (SSHError, ValueError, OSError):
        return {"state": "failed", "execution_outcome": "unknown", "next_step": _RETRY,
                "error": "Installation interrompue ; resultat distant inconnu."}
    if remote.rc == 0 and "RTK_INSTALL_DONE" in remote.stdout:
        return {"state": "installed", "version": "rtk " + release.version,
                "path": posixpath.join(connection.home, _INSTALL_DIRECTORY, "rtk"),
                "archive_sha256": release.archive_sha256, "binary_sha256": release.binary_sha256}
    detail = re.findall(r"^RTK_INSTALL_FAILED (.*)$", remote.stdout, re.M)
    known = remote.rc in _FAILURES
    return {"state": "failed", "execution_outcome": "failed" if known else "unknown", "exit_code": remote.rc,
            "error": _FAILURES.get(remote.rc, "Installation au resultat incertain"),
            "detail": detail[-1][:200] if detail else remote.stdout[-200:], "next_step": _RETRY}


def provision(connection, deadline: Deadline | None = None) -> dict:
    """Premier besoin : installe au plus une fois par compte et par processus, sans lever."""
    if not auto_install_enabled():
        return {"state": "disabled", "message": "ROMEO_RTK_AUTO_INSTALL desactive l'installation automatique."}
    if not _attempts_lock.acquire(blocking=False):
        return {"state": "in_progress", "message": "Installation de RTK deja en cours ; commande en mode brut."}
    started = time.monotonic()
    try:
        key = (connection.host, connection.user)
        previous = _attempts.get(key)
        if previous is not None:
            return {**previous, "attempted_now": False}
        result = attempt(connection)
        result["duration_seconds"] = round(time.monotonic() - started, 2)
        if result["state"] != "in_progress":
            _attempts[key] = result
        return {**result, "attempted_now": True}
    except SSHError:
        return {"state": "failed", "execution_outcome": "unknown", "next_step": _RETRY,
                "error": "Compte SSH illisible ; installation non tentee."}
    finally:
        _attempts_lock.release()
        if deadline is not None:
            deadline.extend(time.monotonic() - started)


def find_binary(connection, run, deadline: Deadline, cwd: str | None = None) -> str | None:
    """La session persistante peut avoir un PATH anterieur a l'installation."""
    candidate = shlex.quote(posixpath.join(connection.home, _INSTALL_DIRECTORY, "rtk"))
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
    install = None
    if binary is None:
        install = provision(connection, deadline)
        binary = install.get("path")
    metadata = {"requested": True, "available": binary is not None, "applied": False,
                "path": binary, "reason": "not_installed"}
    if install is not None:
        metadata["install"] = install
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
