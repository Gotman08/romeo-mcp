#!/usr/bin/env python3
"""Regenere les verrous de dependances, epingles par hash pour tous les systemes.

`server.lock` fige les dependances du serveur et `verifier.lock` celles du
verificateur d'attestations. Ils sont livres dans la wheel : l'attestation d'une
release couvre donc aussi les dependances qu'elle installera.

Usage (uv requis) :
    python tools/lock_dependencies.py            # conserve les versions deja figees
    python tools/lock_dependencies.py --upgrade  # reprend les dernieres versions
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LOCKS = ROOT / "romeo_mcp" / "locks"
#: Le verificateur reste hors des dependances du serveur.
VERIFIER_REQUIREMENTS = "sigstore>=4.5,<5\n"


def compile_lock(source: Path, output: Path, upgrade: bool) -> None:
    # uv garde les versions du fichier de sortie existant, sauf --upgrade.
    command = ["uv", "pip", "compile", str(source), "--universal", "--generate-hashes",
               "--python-version", "3.11", "--no-header", "--no-annotate", "--quiet",
               "--output-file", str(output)]
    if upgrade:
        command.append("--upgrade")
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upgrade", action="store_true", help="reprendre les dernieres versions autorisees")
    args = parser.parse_args()
    LOCKS.mkdir(exist_ok=True)
    compile_lock(ROOT / "pyproject.toml", LOCKS / "server.lock", args.upgrade)
    with tempfile.TemporaryDirectory() as temporary:
        source = Path(temporary) / "verifier.in"
        source.write_text(VERIFIER_REQUIREMENTS, encoding="utf-8")
        compile_lock(source, LOCKS / "verifier.lock", args.upgrade)
    for path in sorted(LOCKS.glob("*.lock")):
        print(path.name, sum(1 for line in path.read_text(encoding="utf-8").splitlines() if "==" in line), "paquets")


if __name__ == "__main__":
    main()
