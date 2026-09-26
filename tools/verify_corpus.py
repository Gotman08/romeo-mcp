#!/usr/bin/env python3
"""Contrôle d'intégrité du corpus de documentation aspiré.

Vérifie ce qui rend un corpus réellement exploitable par un modèle :
liens et images résolvables, absence d'octets parasites, et surtout
**accessibilité** : chaque page doit être atteignable depuis le sommaire,
sans quoi elle est invisible en pratique.

Usage :
    python tools/verify_corpus.py [chemin_du_corpus]
"""

from __future__ import annotations

import re
import sys
import json
import hashlib
from collections import deque
from pathlib import Path

# Cibles de lien markdown, sous forme nue ou entre chevrons CommonMark
# (`[texte](<chemin avec espaces>)`).
LIEN = re.compile(r"(?<!!)\[[^\]]*\]\(\s*(?:<([^>]+)>|([^)\s]+))\s*\)")
IMAGE = re.compile(r"!\[[^\]]*\]\(\s*(?:<([^>]+)>|([^)\s]+))")

#: En deçà, une page n'apporte rien à une recherche documentaire.
SEUIL_PAGE_VIDE = 200


def cible(match: re.Match) -> str:
    return (match.group(1) or match.group(2) or "").strip()


def sans_ancre(href: str) -> str:
    return href.split("#", 1)[0]


def est_interne(href: str) -> bool:
    return bool(href) and not href.startswith(("http://", "https://", "mailto:", "#"))


def corps_utile(texte: str) -> str:
    """Contenu réel d'une page : sans front matter, titres ni navigation."""
    corps = re.sub(r"^---\n.*?\n---\n", "", texte, count=1, flags=re.S)
    corps = re.sub(r"^\[Sommaire\].*$", "", corps, count=1, flags=re.M)
    corps = re.sub(r"^## Dans cette section.*", "", corps, flags=re.S)
    corps = re.sub(r"^#.*$", "", corps, flags=re.M)
    return corps.strip()


def main(racine: Path) -> int:
    if not racine.is_dir():
        print("corpus introuvable : {}".format(racine))
        return 2

    pages = sorted(racine.rglob("*.md"))
    if not pages:
        print("aucune page dans {}".format(racine))
        return 2

    problemes: list[str] = []
    manifest_path = racine / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        actual = {p.relative_to(racine).as_posix() for p in racine.rglob("*")
                  if p.is_file() and p.name != "manifest.json"}
        recorded = set(manifest.get("files", {}))
        if actual != recorded:
            problemes.append("inventaire du corpus different du manifeste")
        for name, expected in manifest.get("files", {}).items():
            path = (racine / name).resolve()
            if not path.is_relative_to(racine.resolve()) or not path.is_file():
                problemes.append(f"fichier du manifeste absent ou hors corpus : {name}")
            elif hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                problemes.append(f"empreinte differente du manifeste : {name}")
        if manifest.get("errors"):
            problemes.append("le manifeste signale une collecte incomplete")
    else:
        problemes.append("manifest.json absent : provenance du corpus non verifiable")
    textes = {p: p.read_text(encoding="utf-8", errors="replace") for p in pages}

    # 1. Octets NUL : ils font classer le fichier comme binaire et le rendent
    #    invisible aux outils de recherche.
    binaires = [p for p in pages if b"\x00" in p.read_bytes()]
    for p in binaires:
        problemes.append("octet NUL dans {}".format(p.relative_to(racine).as_posix()))

    # 2. Liens et images
    liens_ok = liens_ko = img_ok = img_ko = 0
    for page, texte in textes.items():
        for motif, compteur in ((IMAGE, "img"), (LIEN, "lien")):
            for match in motif.finditer(texte):
                href = sans_ancre(cible(match))
                if not est_interne(href):
                    continue
                if compteur == "lien" and not href.endswith(".md"):
                    continue
                if (page.parent / href).resolve().exists():
                    if compteur == "img":
                        img_ok += 1
                    else:
                        liens_ok += 1
                else:
                    if compteur == "img":
                        img_ko += 1
                    else:
                        liens_ko += 1
                    problemes.append(
                        "{} mort dans {} -> {}".format(
                            compteur, page.relative_to(racine).as_posix(), href
                        )
                    )

    # 3. Accessibilité depuis le sommaire : une page qu'aucun chemin n'atteint
    #    est invisible en pratique, même si son fichier existe.
    sommaire = racine / "SOMMAIRE.md"
    atteintes: set[Path] = set()
    if sommaire.exists():
        file = deque([sommaire.resolve()])
        atteintes.add(sommaire.resolve())
        while file:
            courant = file.popleft()
            texte = textes.get(courant) or courant.read_text(
                encoding="utf-8", errors="replace"
            )
            for match in LIEN.finditer(texte):
                href = sans_ancre(cible(match))
                if not est_interne(href) or not href.endswith(".md"):
                    continue
                voisin = (courant.parent / href).resolve()
                if voisin.exists() and voisin not in atteintes:
                    atteintes.add(voisin)
                    file.append(voisin)
    else:
        problemes.append("SOMMAIRE.md absent : le corpus n'a pas de point d'entree")

    orphelines = [
        p for p in pages
        if p.resolve() not in atteintes and p.name != "README.md"
    ]
    for p in orphelines:
        problemes.append(
            "page inaccessible depuis le sommaire : {}".format(
                p.relative_to(racine).as_posix()
            )
        )

    # 4. Pages sans contenu : signalees, mais ce sont des ebauches en amont et
    #    non un defaut d'aspiration.
    vides = [p for p in pages if len(corps_utile(textes[p])) < SEUIL_PAGE_VIDE]

    # --- rapport ------------------------------------------------------------
    print("Corpus : {}".format(racine))
    print("  pages                    : {}".format(len(pages)))
    print("  images resolvables       : {} (cassees : {})".format(img_ok, img_ko))
    print("  liens internes resolvables: {} (cassees : {})".format(liens_ok, liens_ko))
    print("  fichiers avec octet NUL  : {}".format(len(binaires)))
    # `README.md` decrit le corpus, il n'en fait pas partie : il pointe vers le
    # sommaire sans que l'inverse ait de sens.
    documentaires = {p.resolve() for p in pages if p.name != "README.md"}
    print("  atteignables du sommaire : {} / {}".format(
        len(atteintes & documentaires), len(documentaires)))
    print("  pages sans contenu utile : {} (ebauches amont, informatif)".format(
        len(vides)))

    if problemes:
        print()
        print("{} probleme(s) :".format(len(problemes)))
        for p in problemes[:40]:
            print("  - {}".format(p))
        if len(problemes) > 40:
            print("  ... et {} autre(s)".format(len(problemes) - 40))
        return 1

    print()
    print("CORPUS CONFORME")
    return 0


if __name__ == "__main__":
    chemin = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        Path(__file__).resolve().parents[1] / "romeo_mcp" / "documentation"
    )
    raise SystemExit(main(chemin))
