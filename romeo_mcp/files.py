"""Transferts de fichiers entre la machine locale et ROMEO.

``rsync`` est prefere quand il est present (transfert incremental, utile pour
resynchroniser un repertoire de resultats), avec repli sur ``scp`` qui est
toujours livre avec OpenSSH.

Ces transferts ouvrent leur propre connexion SSH : ils ne passent pas par la
session persistante, dont le protocole a sentinelles est concu pour du texte.
"""

from __future__ import annotations

import hashlib
import shlex
import shutil
import subprocess
from pathlib import Path

from .ssh import SSHError

_TRANSFER_TIMEOUT = 900  # 15 min : un resultat de simulation peut etre lourd.


def _has_rsync() -> bool:
    return shutil.which("rsync") is not None


def _run(argv: list[str], what: str) -> str:
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_TRANSFER_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        raise SSHError(
            "{} a depasse {} s. Pour un volume important, lance plutot une "
            "archive cote cluster puis transfere-la.".format(what, _TRANSFER_TIMEOUT)
        ) from exc

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        # Le rappel post-quantique d'OpenSSH 10 pollue toutes les sorties.
        detail = "\n".join(
            line
            for line in detail.splitlines()
            if "post-quantum" not in line
            and "store now" not in line
            and line.strip() not in ("", "**")
        )
        raise SSHError("{} a echoue (code {}) :\n{}".format(what, proc.returncode, detail))
    return (proc.stdout or "").strip()


def empreinte_locale(chemin: Path, algorithme: str = "sha256") -> str:
    """Empreinte d'un fichier local, calculee par blocs."""
    resume = hashlib.new(algorithme)
    with chemin.open("rb") as flux:
        for bloc in iter(lambda: flux.read(1 << 20), b""):
            resume.update(bloc)
    return resume.hexdigest()


def commande_empreinte(chemin: str, algorithme: str = "sha256") -> str:
    """Commande distante donnant l'empreinte d'un fichier.

    Sans tube : dans `... | cut`, le code de retour lu est celui de `cut`, qui
    reussit toujours. Un fichier absent ou illisible passait donc pour un
    transfert corrompu, et l'appelant relançait indefiniment un transfert qui
    ne pouvait pas aboutir. Le decoupage se fait cote Python.
    """
    return "{}sum {}".format(algorithme, shlex.quote(chemin))


def empreinte_depuis_sortie(sortie: str) -> str:
    """Extrait l'empreinte de la sortie de `<algo>sum`, ou rend une chaine vide."""
    premier = (sortie or "").strip().split()
    # `sha256sum` ecrit « <empreinte>  <chemin> » ; toute autre forme signale
    # une erreur qu'il ne faut pas prendre pour une empreinte.
    if premier and len(premier[0]) >= 32 and all(
        c in "0123456789abcdefABCDEF" for c in premier[0]
    ):
        return premier[0].lower()
    return ""


def upload(host: str, local_path: str, remote_path: str) -> dict:
    """Envoie un fichier ou un repertoire local vers ROMEO."""
    source = Path(local_path).expanduser()
    if not source.exists():
        raise SSHError("fichier local introuvable : {}".format(source))

    target = "{}:{}".format(host, remote_path)
    if _has_rsync():
        argv = ["rsync", "-az", "--partial", str(source), target]
        mode = "rsync"
    else:
        argv = ["scp", "-q", "-o", "BatchMode=yes"]
        if source.is_dir():
            argv.append("-r")
        argv += [str(source), target]
        mode = "scp"

    _run(argv, "envoi de {}".format(source.name))
    size = (
        sum(f.stat().st_size for f in source.rglob("*") if f.is_file())
        if source.is_dir()
        else source.stat().st_size
    )
    return {
        "sent": str(source),
        "to": remote_path,
        "bytes": size,
        "transport": mode,
    }


def download(host: str, remote_path: str, local_path: str, recursive: bool = False) -> dict:
    """Rapatrie un fichier ou un repertoire depuis ROMEO."""
    destination = Path(local_path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)

    source = "{}:{}".format(host, remote_path)
    if _has_rsync():
        argv = ["rsync", "-az", "--partial", source, str(destination)]
        mode = "rsync"
    else:
        argv = ["scp", "-q", "-o", "BatchMode=yes"]
        if recursive:
            argv.append("-r")
        argv += [source, str(destination)]
        mode = "scp"

    _run(argv, "recuperation de {}".format(remote_path))
    size = destination.stat().st_size if destination.is_file() else None
    return {
        "downloaded": remote_path,
        "to": str(destination),
        "bytes": size,
        "transport": mode,
    }
