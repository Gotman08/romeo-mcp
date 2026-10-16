#!/usr/bin/env python3
"""Contrôle d'intégrité du corpus de documentation aspiré.

Vérifie ce qui rend un corpus réellement exploitable par un modèle :
liens et images résolvables (avec la casse exacte des noms de fichiers),
ancres `#fragment` qui désignent un titre existant, absence d'octets
parasites, et surtout **accessibilité** : chaque page doit être atteignable
depuis le sommaire, sans quoi elle est invisible en pratique.

Usage :
    python tools/verify_corpus.py [chemin_du_corpus]
"""

from __future__ import annotations

import html
import os
import re
import sys
import json
import hashlib
import unicodedata
import urllib.parse
from collections import deque
from pathlib import Path

# Cibles de lien markdown, sous forme nue ou entre chevrons CommonMark
# (`[texte](<chemin avec espaces>)`).
LIEN = re.compile(r"(?<!!)\[[^\]]*\]\(\s*(?:<([^>]+)>|([^)\s]+))\s*\)")
IMAGE = re.compile(r"!\[[^\]]*\]\(\s*(?:<([^>]+)>|([^)\s]+))")

#: Lien d'ancrage que Docusaurus accole à chaque titre : `[U+200B](#id "Lien direct ...")`.
LIEN_ANCRE = re.compile(r'\[\u200b?\]\(#([^)\s"]+)(?:\s+"[^"]*")?\)')
TITRE = re.compile(r"^ {0,3}#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*$")
CLOTURE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
BALISE_ID = re.compile(r'<[A-Za-z][^>]*?\s(?:id|name)="([^"]+)"')

#: En deçà, une page n'apporte rien à une recherche documentaire.
SEUIL_PAGE_VIDE = 200


def cible(match: re.Match) -> str:
    return (match.group(1) or match.group(2) or "").strip()


def sans_ancre(href: str) -> str:
    return href.split("#", 1)[0]


def est_interne(href: str) -> bool:
    return bool(href) and not href.startswith(("http://", "https://", "mailto:", "#"))


def casse_exacte(racine: Path, chemin: Path, listings: dict[str, frozenset[str]]) -> bool:
    """Vrai si chaque composant de `chemin` existe avec la casse du disque.

    Windows et macOS acceptent `Services.md` pour `services.md`, Linux non : un
    lien correct sur le poste du contributeur est alors mort sur le serveur et
    dans la CI. Hors du corpus, seule l'existence compte, déjà vérifiée.
    """
    base = os.path.normpath(racine)
    try:
        relatif = os.path.relpath(os.path.normpath(chemin), base)
    except ValueError:  # autre lecteur Windows
        return True
    morceaux = relatif.split(os.sep)
    if morceaux[0] == os.pardir or relatif == os.curdir:
        return True
    courant = base
    for nom in morceaux:
        if courant not in listings:
            try:
                listings[courant] = frozenset(
                    unicodedata.normalize("NFC", entree) for entree in os.listdir(courant)
                )
            except OSError:
                return False
        if unicodedata.normalize("NFC", nom) not in listings[courant]:
            return False
        courant = os.path.join(courant, nom)
    return True


def ancre(titre: str) -> str:
    """Identifiant d'un titre, selon le calcul de GitHub et de Docusaurus."""
    texte = LIEN_ANCRE.sub("", titre)
    texte = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", texte)
    texte = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", texte)
    texte = re.sub(r"<[^>]+>", "", texte)
    texte = html.unescape(texte).replace("\u200b", "")
    texte = re.sub(r"[`*]", "", texte)
    texte = unicodedata.normalize("NFC", texte).strip().lower()
    # Le trait bas reste (`x86\_64` donne `x86_64`), la barre d'échappement et la
    # ponctuation tombent, chaque espace devient un tiret.
    return re.sub(r"[^\w\- ]", "", texte).replace(" ", "-")


def ancres_de(texte: str) -> set[str]:
    """Ancres d'une page : titres (calcul GitHub et ids Docusaurus) et balises `id`.

    Un titre répété reçoit le suffixe `-1`, `-2`... comme sur le site.
    """
    trouvees: set[str] = set()
    vus: dict[str, int] = {}
    cloture = ""
    for ligne in re.split(r"\r?\n", texte):
        marque = CLOTURE.match(ligne)
        if marque:
            symbole = marque.group(1)[0]
            if not cloture:
                cloture = symbole
            elif symbole == cloture:
                cloture = ""
            continue
        if cloture:
            continue
        titre = TITRE.match(ligne)
        if not titre:
            continue
        trouvees.update(LIEN_ANCRE.findall(titre.group(1)))
        base = ancre(titre.group(1))
        rang = vus.get(base, 0)
        vus[base] = rang + 1
        trouvees.add(base if rang == 0 else "{}-{}".format(base, rang))
    trouvees.update(BALISE_ID.findall(texte))
    return trouvees


def ancre_resolue(fragment: str, disponibles: set[str]) -> bool:
    """Vrai si `fragment` désigne une ancre de la page, brut ou décodé."""
    # `#top` et le fragment vide désignent le haut de page (spécification HTML).
    if fragment.lower() == "top" or fragment.startswith(":~:"):
        return True
    variantes = {fragment, urllib.parse.unquote(fragment)}
    return any(unicodedata.normalize("NFC", v) in disponibles for v in variantes)


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

    # 2. Liens, images et ancres
    liens_ok = liens_ko = img_ok = img_ko = ancres_ok = ancres_ko = 0
    listings: dict[str, frozenset[str]] = {}
    ancres_par_page: dict[Path, set[str]] = {}
    textes_resolus = {p.resolve(): t for p, t in textes.items()}
    racine_resolue = racine.resolve()
    for page, texte in textes.items():
        nom_page = page.relative_to(racine).as_posix()
        for motif, compteur in ((IMAGE, "img"), (LIEN, "lien")):
            for match in motif.finditer(texte):
                href, _, fragment = cible(match).partition("#")
                voisine = None  # page Markdown du corpus dont l'ancre est a verifier
                if not href and fragment and compteur == "lien":
                    voisine = page.resolve()  # ancre dans la page elle-meme
                elif est_interne(href):
                    # Toute cible locale doit exister, quelle que soit son extension :
                    # un `.md` place apres l'ancre (`page#ancre.md`) passait inapercu.
                    chemin = page.parent / href
                    existe = chemin.resolve().exists()
                    if existe and casse_exacte(racine, chemin, listings):
                        if compteur == "img":
                            img_ok += 1
                        else:
                            liens_ok += 1
                        cible_md = chemin.resolve()
                        if cible_md.suffix == ".md" and cible_md.is_relative_to(racine_resolue):
                            voisine = cible_md
                    else:
                        if compteur == "img":
                            img_ko += 1
                        else:
                            liens_ko += 1
                        problemes.append(
                            "{} mort dans {} -> {}{}".format(
                                compteur, nom_page, href,
                                " (casse differente de celle du disque)" if existe else "",
                            )
                        )
                else:
                    continue

                # Une ancre doit designer un titre de la page visee.
                if voisine is None or not fragment or compteur != "lien":
                    continue
                if voisine not in ancres_par_page:
                    contenu = textes_resolus.get(voisine)
                    if contenu is None:
                        contenu = voisine.read_text(encoding="utf-8", errors="replace")
                    ancres_par_page[voisine] = ancres_de(contenu)
                if ancre_resolue(fragment, ancres_par_page[voisine]):
                    ancres_ok += 1
                else:
                    ancres_ko += 1
                    problemes.append(
                        "ancre introuvable dans {} -> {}#{}".format(nom_page, href, fragment)
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
    print("  ancres resolvables       : {} (introuvables : {})".format(ancres_ok, ancres_ko))
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
