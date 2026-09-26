# Copyright (c) 2026 Gotman08 (MIT)
"""Configuration utilisateur, conservee hors du depot et sans identifiants secrets."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path


FIELDS = {"ROMEO_HOST", "ROMEO_ACCOUNT", "ROMEO_QOS", "ROMEO_TOOL_PROFILE"}


def config_path() -> Path:
    override = os.environ.get("ROMEO_CONFIG")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return base / "romeo-mcp" / "config.json"


def load() -> dict[str, str]:
    path = config_path()
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or any(k not in FIELDS or not isinstance(v, str) for k, v in data.items()):
        raise ValueError("Configuration ROMEO invalide : utiliser la commande configure.")
    return data


def setting(name: str, default: str = "") -> str:
    return os.environ[name] if name in os.environ else load().get(name, default)


def save(values: dict[str, str]) -> Path:
    for key, value in values.items():
        if key == "ROMEO_TOOL_PROFILE" and value not in {"essential", "full"}:
            raise ValueError("Profil d'outils inconnu : choisir essential ou full.")
        if key not in FIELDS or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value):
            raise ValueError("Hote, compte et QOS doivent etre des identifiants simples, sans espace ni commande.")
        if key == "ROMEO_ACCOUNT" and value.upper() in {"VOTRE_PROJET", "YOUR_PROJECT", "R000000"}:
            raise ValueError("Remplacer VOTRE_PROJET par le code reel du projet autorise dans le portail ROMEO.")
    data = {**load(), **values}
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, mode="w", encoding="utf-8", newline="\n", delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    try:
        if os.name != "nt":
            temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path
