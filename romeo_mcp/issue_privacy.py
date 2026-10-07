"""Rapports publics : filtrer le texte fourni, sans lire les logs ou SSH."""
from __future__ import annotations

import getpass
import os
from pathlib import Path
import re
import socket

from . import config
from .privacy import REDACTED, redact_text

_PATH = re.compile(r"(?i)(?:\b[a-z]:[\\/]|\\\\[^\s\\]+\\|(?<!\w)[~/](?:[\w.~-]+/|[\w.~-]+\\)?)[^\s<>\"'`;,]*")
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_IP = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b|(?<!\w)(?:[a-fA-F0-9]{0,4}:){2,}[a-fA-F0-9:]+(?!\w)")
_URL = re.compile(r"\b(?:https?|ssh|sftp|file)://[^\s<>\"'`]+", re.I)
_DETAIL = re.compile(r"(?im)^.*(?:ROMEO_(?:ACCOUNT|HOST|QOS|HOME|SCRATCH)\s*[:=]|(?:user(?:name)?|account|host(?:name)?|project|job[_ -]?id)\s*[:=]).*$")
_JOB = re.compile(r"(?i)\b(?:job(?:[_ -]?id)?|allocation|Slurm)\s*(?:#|[:=])?\s*\d{2,}\b")


def private_values() -> list[str]:
    # On ne charge ni ~/.ssh/config, ni les credentials GitHub, ni l'environnement
    # complet dans le rapport. Ces valeurs servent seulement au remplacement.
    try:
        saved = config.load()
    except (ValueError, OSError):
        raise ValueError("Configuration privee illisible ; impossible de filtrer le rapport avant envoi.") from None
    values = [str(Path.home()), getpass.getuser(), socket.gethostname()]
    names = ("ROMEO_ACCOUNT", "ROMEO_HOST", "ROMEO_QOS", "ROMEO_HOME", "ROMEO_SCRATCH", "ROMEO_GITHUB_TOKEN")
    values.extend(os.environ.get(name, saved.get(name, "")) for name in names)
    # Autres secrets explicitement identifies : ils ne doivent pas reapparaitre
    # dans du texte libre, meme sans affectation `TOKEN=...`.
    values.extend(value for name, value in os.environ.items()
                  if re.search(r"TOKEN|PASSWORD|SECRET|API_KEY|CREDENTIAL", name, re.I))
    return sorted({v for v in values if isinstance(v, str) and v}, key=len, reverse=True)


def public_text(value: str, maximum: int, *, secrets: list[str]) -> tuple[str, bool]:
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError(f"Texte de rapport attendu, limite {maximum} caracteres ; ne pas joindre de journal brut.")
    # Filtrer AVANT toute normalisation : ne pas couper une cle multiline ou
    # une affectation avant de l'avoir reconnue.
    clean = redact_text(value)
    for secret in secrets:
        pattern = re.escape(secret) if len(secret) >= 3 else r"(?<!\w)" + re.escape(secret) + r"(?!\w)"
        clean = re.sub(pattern, REDACTED, clean, flags=re.I)
    for pattern in (_URL, _PATH, _EMAIL, _IP, _DETAIL, _JOB):
        clean = pattern.sub(REDACTED, clean)
    clean = "".join(c for c in clean if c in "\n\t" or (c.isprintable() and c not in "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"))
    clean = clean.replace("@", "[at]").strip()
    if not clean:
        raise ValueError("Le rapport doit contenir une description technique apres filtrage.")
    return clean, clean != value.strip()
