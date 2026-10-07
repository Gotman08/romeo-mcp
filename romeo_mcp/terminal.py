"""Explicit launcher for Ratatui; importing the MCP never loads this module."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def add_arguments(parser) -> None:
    parser.add_argument("--demo", action="store_true", help="données fictives, sans lire votre configuration")
    parser.add_argument("--build", action="store_true", help="compiler explicitement le binaire optionnel avec Cargo")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", help="exporter un relevé local sans ouvrir de terminal")
    output.add_argument("--snapshot", action="store_true", help="rendu Ratatui en texte, sans terminal interactif")
    parser.add_argument("--binary", default="", help="chemin d'un binaire romeo-tui déjà compilé")
    parser.add_argument("--db", type=Path, help="registre local alternatif, ouvert en lecture seule")
    parser.add_argument("--refresh", type=int, default=5, metavar="SECONDES", help="relecture locale toutes les 5 s par défaut")
    parser.add_argument("--limit", type=int, default=40, help="nombre de jobs/transferts, entre 1 et 100")
    parser.add_argument("--view", choices=("overview", "jobs", "transfers", "updates"), default="overview")
    parser.add_argument("--width", type=int, default=100, help="largeur du rendu --snapshot")
    parser.add_argument("--height", type=int, default=30, help="hauteur du rendu --snapshot")


def run(args) -> int:
    if not 1 <= args.refresh <= 300 or not 1 <= args.limit <= 100:
        raise ValueError("--refresh : 1 à 300 secondes ; --limit : 1 à 100")
    if not 40 <= args.width <= 240 or not 10 <= args.height <= 80:
        raise ValueError("--width : 40 à 240 ; --height : 10 à 80")
    if args.json:
        if args.build:
            raise ValueError("--json ne nécessite pas de compilation ; retirer --build")
        from .terminal_data import snapshot
        print(json.dumps(snapshot(db=args.db, limit=args.limit, demo=args.demo),
                         indent=2, ensure_ascii=True, allow_nan=False))
        return 0
    if not args.snapshot and (not sys.stdin.isatty() or not sys.stdout.isatty()):
        raise ValueError("Ouvrir un terminal interactif, ou utiliser tui --demo --snapshot / --json.")
    root = Path(__file__).resolve().parent.parent
    manifest = root / "terminal" / "Cargo.toml"
    executable = "romeo-tui.exe" if os.name == "nt" else "romeo-tui"
    built = manifest.parent / "target" / "release" / executable
    if args.build:
        if not manifest.is_file():
            raise ValueError("Sources Rust absentes : compiler depuis le dépôt, puis passer --binary CHEMIN.")
        cargo = shutil.which("cargo")
        if not cargo:
            candidate = Path.home() / ".cargo/bin" / ("cargo.exe" if os.name == "nt" else "cargo")
            cargo = str(candidate) if candidate.is_file() else None
        if not cargo:
            raise ValueError("Installer Rust 1.88+ depuis https://rustup.rs, puis relancer tui --build.")
        compiled = subprocess.run([cargo, "build", "--locked", "--release", "--manifest-path", str(manifest),
                                   "--target-dir", str(manifest.parent / "target")], cwd=root)
        if compiled.returncode:
            raise ValueError("Compilation de l'interface échouée ; consulter les messages Cargo ci-dessus.")
    explicit = args.binary or os.environ.get("ROMEO_TUI_BINARY", "")
    binary = str(Path(explicit).expanduser().absolute()) if explicit else (
        str(built) if built.is_file() else shutil.which("romeo-tui"))
    if not binary or not Path(binary).is_file():
        raise ValueError("Interface optionnelle non compilée. Depuis le dépôt : python -m romeo_mcp tui --build --demo")
    command = [binary, "--python", sys.executable, "--package-root", str(root),
               "--refresh", str(args.refresh), "--limit", str(args.limit), "--view", args.view]
    if args.demo:
        command.append("--demo")
    if args.db:
        command.extend(["--db", str(args.db.expanduser().absolute())])
    if args.snapshot:
        command.extend(["--snapshot", "--width", str(args.width), "--height", str(args.height)])
    try:
        return subprocess.run(command).returncode
    except KeyboardInterrupt:
        return 130
