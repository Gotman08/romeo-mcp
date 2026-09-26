#!/usr/bin/env python3
"""Lance toutes les suites de tests et agrege leurs verdicts.

Chaque suite tourne dans son propre processus : une suite qui plante ou qui
appelle `sys.exit` n'emporte pas les autres, et l'etat global d'un module
(session SSH, caches) ne fuit pas d'une suite a la suivante.

Par defaut, seules les suites hors ligne sont executees. Les suites qui
parlent au cluster soumettent de vrais jobs et prennent plusieurs minutes :
elles s'ajoutent explicitement avec `--live`.

Usage :
    python tests/run_all.py              # suites hors ligne
    python tests/run_all.py --live       # + suites cluster
    python tests/run_all.py --only units # une seule suite
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]

#: (cle, chemin, description, besoin du cluster)
SUITES = [
    ("units", "tests/test_units.py",
     "durees, partitions, architectures, sbatch, garde-fous", False),
    ("workloads", "tests/test_workloads.py",
     "diagnostic, lanceurs, gabarits, materiel", False),
    ("regressions", "tests/test_regressions.py",
     "defauts constates : ils doivent rester corriges", False),
    ("ajouts", "tests/test_ajouts.py",
     "enchainements de jobs, controle de derive du modele", False),
    ("docs", "tests/test_docs.py",
     "recherche, contexte, pagination, portabilite et protocole documentaire", False),
    ("setup", "tests/test_setup.py",
     "configuration privee, allocation explicite et confidentialite", False),
    ("accompagnement", "tests/test_accompagnement.py",
     "profils MCP, diagnostic distant simule et reproductibilite privee", False),
    # `protocol` appelle romeo_status a travers le protocole : la poignee de
    # main est hors ligne, l'appel d'outil ne l'est pas. Le classer hors ligne
    # rendait un checkout neuf rouge pour une raison qui n'est pas un defaut.
    ("protocol", "tests/smoke_protocol.py",
     "poignee de main MCP en stdio", True),
    # Le corpus est livre avec le projet : aucune collecte reseau necessaire.
    ("corpus", "tools/verify_corpus.py",
     "integrite de la documentation embarquee", False),
    ("ssh", "tests/smoke_ssh.py",
     "transport SSH persistant", True),
    ("live", "tests/smoke_live.py",
     "bout en bout : soumission, suivi, efficacite", True),
    ("repro-live", "tests/smoke_repro_live.py",
     "fiche de reproductibilite d'un petit calcul CPU reel", True),
    ("workloads-live", "tests/smoke_workloads_live.py",
     "jobs defaillants, tableaux, telemetrie", True),
]


def executer(chemin: str, live: bool = False) -> tuple[int, float]:
    """Execute une suite et rend son code de sortie et sa duree."""
    debut = time.monotonic()
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    if not live:
        env.update(ROMEO_ACCOUNT="test-project", ROMEO_HOST="invalid-offline-host", ROMEO_QOS="normal",
                   ROMEO_TOOL_PROFILE="full")
    # `PYTHONIOENCODING` : les suites impriment des accents, et la console
    # Windows par defaut ne les encode pas.
    proc = subprocess.run(
        [sys.executable, chemin],
        cwd=str(RACINE),
        env=env,
    )
    return proc.returncode, time.monotonic() - debut


def main() -> int:
    parseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parseur.add_argument("--live", action="store_true",
                         help="inclure les suites qui parlent au cluster")
    parseur.add_argument("--only", default="",
                         help="ne lancer qu'une suite : {}".format(
                             ", ".join(cle for cle, *_ in SUITES)))
    args = parseur.parse_args()

    if args.only:
        choisies = [s for s in SUITES if s[0] == args.only]
        if not choisies:
            raise SystemExit("suite inconnue : {}. Valeurs : {}".format(
                args.only, ", ".join(cle for cle, *_ in SUITES)))
    else:
        # Les suites qui parlent au cluster soumettent de vrais jobs : elles ne
        # tournent que sur demande explicite.
        choisies = [s for s in SUITES if args.live or not s[3]]

    print("=" * 68)
    print("Suites a executer : {}".format(", ".join(c for c, *_ in choisies)))
    if not args.live and not args.only:
        print("(suites cluster ignorees ; ajoute --live pour les inclure)")
    print("=" * 68)

    resultats = []
    for cle, chemin, description, live in choisies:
        print("\n>>> {} : {}".format(cle, description))
        print("-" * 68)
        if not (RACINE / chemin).exists():
            print("  ABSENTE : {}".format(chemin))
            resultats.append((cle, 2, 0.0))
            continue
        code, duree = executer(chemin, live)
        resultats.append((cle, code, duree))

    print()
    print("=" * 68)
    print("BILAN")
    print("=" * 68)
    for cle, code, duree in resultats:
        etat = "OK" if code == 0 else "ECHEC (code {})".format(code)
        print("  {:<16} {:<18} {:.1f} s".format(cle, etat, duree))

    echecs = [cle for cle, code, _ in resultats if code != 0]
    print()
    if echecs:
        print("{} suite(s) en echec : {}".format(len(echecs), ", ".join(echecs)))
        return 1
    print("Toutes les suites passent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
