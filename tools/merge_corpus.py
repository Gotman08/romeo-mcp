#!/usr/bin/env python3
"""Intègre une collecte du site ROMEO dans le corpus versionné du projet.

Le collecteur (`romeo_doc_scraper.py`) écrit les pages officielles brutes. Le
corpus embarqué y ajoute la navigation propre au projet, que cet outil applique
de façon reproductible plutôt que par un script annexe :

- le fil d'Ariane de chaque page se prolonge vers le guide du corpus, les guides
  MCP et le catalogue des outils ;
- chaque page se termine par un pied de retour (haut de page, sommaire, guide) ;
- les ids de titre propres au site (`#article1`), inconnus de GitHub et des
  lecteurs Markdown, deviennent l'ancre calculée depuis le titre, dans le titre
  comme dans les liens qui le visent ;
- `SOMMAIRE.md` garde son en-tête et son pied écrits à la main autour de
  l'arborescence officielle ;
- `manifest.json` reprend la provenance de la collecte et décrit ces ajouts.

Les README de section écrits à la main ne sont jamais modifiés.

Usage :
    python tools/merge_corpus.py COLLECTE            # compare, n'écrit rien
    python tools/merge_corpus.py COLLECTE --write    # intègre, puis vérifie

Codes de sortie : 0 corpus identique (ou intégré et conforme), 1 écarts relevés
ou corpus intégré non conforme, 2 collecte ou corpus inexploitable.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import io
import json
import os
import posixpath
import re
import sys
import tempfile
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

try:
    import verify_corpus  # lancé comme script : le dossier tools/ est sur le chemin
except ImportError:
    from tools import verify_corpus  # importé comme `tools.merge_corpus`

CORPUS = Path(__file__).resolve().parents[1] / "romeo_mcp" / "documentation"

GUIDES_MCP = "https://github.com/Gotman08/romeo-mcp/blob/main/docs/README.md"
TOOLS = "https://github.com/Gotman08/romeo-mcp/blob/main/docs/Tools.md"
SUFFIXE_FIL = " · [Corpus ROMEO]({rel}README.md) · [Guides MCP](" + GUIDES_MCP + ") · [Tools](" + TOOLS + ")"
PIED = "[↑ Haut de page](#{ancre}) · [Sommaire officiel]({rel}SOMMAIRE.md) · [Guide du corpus]({rel}README.md)"
SECTION = "## Dans cette section"
REPERE_SOMMAIRE = "## Toutes les pages officielles\n\n"
SEPARATEUR_PIED = "\n---\n"

#: Cible d'un lien dont l'ancre peut être réécrite : `](chemin#ancre`, avec un
#: chemin vide pour la page elle-même.
LIEN_AVEC_ANCRE = re.compile(r"(\]\(<?)([^)\s>#]*)#([^)\s>]+)")
DATE_PAGE = re.compile(r'^scraped_at: ".*"\n', re.M)

#: Décomptes que le tableau de provenance du README du corpus reprend à la main :
#: (clé du manifeste, libellé de la ligne du tableau, nom affiché).
COMPTES_README = (
    ("pages", r"Pages officielles", "pages officielles"),
    ("images", r"Images conserv\w*", "images"),
)

#: Valeurs de départ du bloc `local_navigation`, quand le corpus n'en a pas encore.
NAVIGATION_PAR_DEFAUT = {
    "origin": "romeo-mcp project",
    "readmes": [],
    "page_navigation": {
        "pages": 0,
        "changes": [
            "MCP guide and Tools links in breadcrumbs",
            "return links in Dans cette section",
        ],
        "official_content_and_collection_metadata_preserved": True,
        "local_anchor_repairs": {},
    },
}


class ErreurFusion(Exception):
    """Collecte ou corpus inexploitable : rien n'est écrit."""


@dataclass
class Plan:
    """Résultat de la fusion, calculé en mémoire avant toute écriture."""

    pages: dict[str, str] = field(default_factory=dict)
    images: dict[str, bytes] = field(default_factory=dict)
    sommaire: str = ""
    manifeste: dict = field(default_factory=dict)
    reparations: dict[str, dict[str, str]] = field(default_factory=dict)
    pages_obsoletes: list[str] = field(default_factory=list)
    images_obsoletes: list[str] = field(default_factory=list)


@dataclass
class Ecarts:
    """Différences entre le corpus et ce que la fusion produirait."""

    pages_nouvelles: list[str] = field(default_factory=list)
    pages_modifiees: list[str] = field(default_factory=list)
    images_nouvelles: list[str] = field(default_factory=list)
    images_modifiees: list[str] = field(default_factory=list)
    obsoletes: list[str] = field(default_factory=list)
    sommaire: bool = False
    manifeste: bool = False

    @property
    def identique(self) -> bool:
        return not (self.pages_nouvelles or self.pages_modifiees or self.images_nouvelles
                    or self.images_modifiees or self.obsoletes or self.sommaire or self.manifeste)


def lire(chemin: Path) -> str:
    return chemin.read_bytes().decode("utf-8")


def ecrire(chemin: Path, contenu: bytes) -> None:
    """Remplacement atomique : un lecteur voit l'ancienne ou la nouvelle version."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=chemin.parent, prefix=".romeo-", delete=False) as flux:
        temporaire = Path(flux.name)
        flux.write(contenu)
    try:
        os.replace(temporaire, chemin)
    finally:
        temporaire.unlink(missing_ok=True)


# -- pages --------------------------------------------------------------------

def reparations_ancres(texte: str) -> dict[str, str]:
    """Ids de titre propres au site -> ancre calculée depuis le titre.

    Docusaurus accepte un id imposé par l'auteur (`{#article1}`). GitHub et les
    lecteurs Markdown calculent l'id d'après le texte du titre : les liens vers
    l'id imposé y restent sans effet.
    """
    resultat: dict[str, str] = {}
    for _, _, _, ids, calcule in verify_corpus.titres(texte):
        for ancien in ids:
            if ancien != calcule:
                resultat["#" + ancien] = "#" + calcule
    return resultat


def reecrire_ancres(cle: str, texte: str, reparations: dict[str, dict[str, str]]) -> str:
    """Remplace, dans les liens, les ancres réparées de cette page ou d'une autre."""
    def remplacer(match: re.Match) -> str:
        debut, chemin, ancre = match.groups()
        if chemin:
            visee = posixpath.normpath(
                posixpath.join(posixpath.dirname(cle), urllib.parse.unquote(chemin)))
        else:
            visee = cle
        nouvelle = reparations.get(visee, {}).get("#" + ancre)
        return match.group(0) if nouvelle is None else "{}{}{}".format(debut, chemin, nouvelle)

    return LIEN_AVEC_ANCRE.sub(remplacer, texte)


def fusionner_page(cle: str, texte: str, reparations: dict[str, dict[str, str]]) -> str:
    """Ajoute à une page brute la navigation du projet."""
    rel = "../" * cle.count("/")
    lignes = texte.split("\n")
    if lignes[0] != "---" or "---" not in lignes[1:]:
        raise ErreurFusion("en-tete absent dans {}".format(cle))
    fin = lignes.index("---", 1)
    fil = next((i for i in range(fin + 1, len(lignes)) if lignes[i].startswith("[Sommaire](")), None)
    if fil is None:
        raise ErreurFusion("fil d'Ariane absent dans {} : collecte incomplete ?".format(cle))
    if "[Corpus ROMEO](" in lignes[fil]:
        raise ErreurFusion("{} contient deja la navigation du projet : fournir la collecte brute".format(cle))
    ancre_titre = next(
        (calcule for _, niveau, _, _, calcule in verify_corpus.titres(texte) if niveau == 1), None)
    if ancre_titre is None:
        raise ErreurFusion("titre de niveau 1 absent dans {}".format(cle))

    lignes[fil] += SUFFIXE_FIL.format(rel=rel)
    texte = reecrire_ancres(cle, "\n".join(lignes), reparations).rstrip("\n")
    pied = PIED.format(ancre=ancre_titre, rel=rel)
    # Une page qui a des enfants porte déjà sa section : le pied s'y ajoute.
    if re.search("^" + re.escape(SECTION) + "$", texte, flags=re.M):
        return texte + "\n\n" + pied + "\n"
    return texte + "\n\n" + SECTION + "\n\n" + pied + "\n"


def fusionner_sommaire(actuel: str | None, brut: str) -> str:
    """Arborescence officielle, entre l'en-tête et le pied écrits à la main."""
    debut = brut.find("\n- ")
    if debut < 0:
        raise ErreurFusion("SOMMAIRE.md de la collecte sans arborescence")
    arbre = brut[debut + 1:].rstrip("\n")
    if actuel is None or REPERE_SOMMAIRE not in actuel:
        return brut  # premier import : aucun en-tete local a conserver
    fin_entete = actuel.index(REPERE_SOMMAIRE) + len(REPERE_SOMMAIRE)
    pied = actuel.find(SEPARATEUR_PIED, fin_entete)
    if pied < 0:
        raise ErreurFusion("pied introuvable dans le SOMMAIRE.md du corpus")
    return actuel[:fin_entete] + arbre + "\n" + actuel[pied:]


# -- collecte et plan ---------------------------------------------------------

def pages_officielles(racine: Path) -> list[str]:
    """Pages issues du site : tout le Markdown sauf README.md et SOMMAIRE.md de la racine."""
    return sorted(
        cle for cle in (p.relative_to(racine).as_posix() for p in racine.rglob("*.md"))
        if cle not in ("README.md", "SOMMAIRE.md")
    )


def pages_du_site(corpus: Path) -> set[str]:
    """Pages du corpus issues du site : leur en-tete porte `source:`, pas celui des README."""
    trouvees = set()
    for cle in pages_officielles(corpus):
        debut = (corpus / cle).read_bytes()[:2000].decode("utf-8", errors="replace")
        if re.search(r'^source: "', debut, flags=re.M):
            trouvees.add(cle)
    return trouvees


def verifier_collecte(brut: Path) -> None:
    """La fusion suppose une collecte saine : liens, ancres, empreintes et sommaire."""
    sortie = io.StringIO()
    with contextlib.redirect_stdout(sortie):
        code = verify_corpus.main(brut)
    if code:
        raise ErreurFusion("la collecte ne passe pas verify_corpus :\n" + sortie.getvalue().rstrip())


def preparer(brut: Path, corpus: Path) -> Plan:
    """Calcule la fusion en mémoire. Lève `ErreurFusion` avant toute écriture."""
    if not brut.is_dir():
        raise ErreurFusion("collecte introuvable : {}".format(brut))
    if not corpus.is_dir():
        raise ErreurFusion("corpus introuvable : {}".format(corpus))
    if brut.resolve() == corpus.resolve():
        raise ErreurFusion("la collecte et le corpus sont le meme dossier")
    try:
        manifeste_brut = json.loads(lire(brut / "manifest.json"))
    except (OSError, ValueError) as erreur:
        raise ErreurFusion("manifest.json de la collecte illisible : {}".format(erreur)) from erreur
    if manifeste_brut.get("errors"):
        raise ErreurFusion("la collecte signale {} erreur(s) : la refaire avant de l'integrer".format(
            manifeste_brut["errors"]))
    verifier_collecte(brut)

    cles = pages_officielles(brut)
    conflits = [cle for cle in cles if cle.endswith("/README.md")]
    if conflits:
        raise ErreurFusion("pages officielles en conflit avec un README local : {}".format(", ".join(conflits)))
    dossier_images = brut / "images"
    images = {
        "images/" + p.name: p.read_bytes()
        for p in sorted(dossier_images.iterdir()) if p.is_file()
    } if dossier_images.is_dir() else {}
    if len(cles) != manifeste_brut.get("pages") or len(images) != manifeste_brut.get("images"):
        raise ErreurFusion("la collecte compte {} page(s) et {} image(s), son manifeste {} et {}".format(
            len(cles), len(images), manifeste_brut.get("pages"), manifeste_brut.get("images")))

    textes = {cle: lire(brut / cle) for cle in cles}
    reparations = {cle: r for cle in cles if (r := reparations_ancres(textes[cle]))}
    plan = Plan(reparations=reparations, images=images)
    plan.pages = {cle: fusionner_page(cle, textes[cle], reparations) for cle in cles}
    sommaire_actuel = corpus / "SOMMAIRE.md"
    plan.sommaire = fusionner_sommaire(
        lire(sommaire_actuel) if sommaire_actuel.is_file() else None, lire(brut / "SOMMAIRE.md"))

    # Etat final du corpus : ce qui existe, moins ce qui a disparu du site, plus la fusion.
    finaux = {
        p.relative_to(corpus).as_posix(): p.read_bytes()
        for p in corpus.rglob("*") if p.is_file() and p.name != "manifest.json"
    }
    plan.pages_obsoletes = sorted(pages_du_site(corpus) - set(cles))
    plan.images_obsoletes = sorted(
        cle for cle in finaux if cle.startswith("images/") and cle != "images/README.md" and cle not in images)
    for cle in plan.pages_obsoletes + plan.images_obsoletes:
        finaux.pop(cle, None)
    finaux.update({cle: texte.encode("utf-8") for cle, texte in plan.pages.items()})
    finaux["SOMMAIRE.md"] = plan.sommaire.encode("utf-8")
    finaux.update(images)

    ancien_manifeste = corpus / "manifest.json"
    ancien = json.loads(lire(ancien_manifeste)) if ancien_manifeste.is_file() else {}
    plan.manifeste = construire_manifeste(manifeste_brut, ancien, finaux, len(cles), reparations)
    return plan


def construire_manifeste(brut: dict, ancien: dict, finaux: dict[str, bytes], pages: int,
                         reparations: dict[str, dict[str, str]]) -> dict:
    """Provenance de la collecte, empreintes du corpus et description des ajouts locaux."""
    local = copy.deepcopy(ancien.get("local_navigation") or NAVIGATION_PAR_DEFAUT)
    local["readmes"] = sorted(
        (cle for cle in finaux if cle == "README.md" or cle.endswith("/README.md")),
        key=lambda cle: (cle != "README.md", cle))
    navigation = local.setdefault("page_navigation", copy.deepcopy(NAVIGATION_PAR_DEFAUT["page_navigation"]))
    navigation["pages"] = pages
    navigation["local_anchor_repairs"] = dict(sorted(reparations.items()))
    navigation.pop("local_link_repairs", None)  # ancien enregistrement d'un script externe
    return {
        "source": brut["source"],
        "publisher": brut["publisher"],
        "retrieved_at": brut["retrieved_at"],
        "pages": pages,
        "images": sum(1 for cle in finaux if cle.startswith("images/") and cle != "images/README.md"),
        "errors": brut["errors"],
        "link_normalization": brut.get("link_normalization", {}),
        "files": {cle: hashlib.sha256(finaux[cle]).hexdigest() for cle in sorted(finaux)},
        "local_navigation": local,
    }


# -- comparaison et écriture --------------------------------------------------

def sans_dates(texte: str) -> str:
    return DATE_PAGE.sub("", texte)


def manifeste_sans_dates(manifeste: dict) -> dict:
    """Le manifeste à comparer : ni date de collecte, ni empreintes (qui suivent les dates)."""
    reduit = {k: v for k, v in manifeste.items() if k not in ("retrieved_at", "files")}
    reduit["files"] = sorted(manifeste.get("files", {}))
    return reduit


def comparer(plan: Plan, corpus: Path) -> Ecarts:
    """Compare le corpus à la fusion, sans tenir compte des dates de collecte."""
    ecarts = Ecarts(obsoletes=plan.pages_obsoletes + plan.images_obsoletes)
    for cle, texte in plan.pages.items():
        chemin = corpus / cle
        if not chemin.is_file():
            ecarts.pages_nouvelles.append(cle)
        elif sans_dates(lire(chemin)) != sans_dates(texte):
            ecarts.pages_modifiees.append(cle)
    for cle, contenu in plan.images.items():
        chemin = corpus / cle
        if not chemin.is_file():
            ecarts.images_nouvelles.append(cle)
        elif chemin.read_bytes() != contenu:
            ecarts.images_modifiees.append(cle)
    chemin = corpus / "SOMMAIRE.md"
    ecarts.sommaire = not chemin.is_file() or lire(chemin) != plan.sommaire
    chemin = corpus / "manifest.json"
    try:
        actuel = json.loads(lire(chemin)) if chemin.is_file() else None
    except ValueError:
        actuel = None
    ecarts.manifeste = actuel is None or manifeste_sans_dates(actuel) != manifeste_sans_dates(plan.manifeste)
    return ecarts


def appliquer(plan: Plan, corpus: Path, supprimer: bool) -> None:
    """Ecrit pages, images et sommaire, puis le manifeste en dernier."""
    for cle, texte in plan.pages.items():
        ecrire(corpus / cle, texte.encode("utf-8"))
    ecrire(corpus / "SOMMAIRE.md", plan.sommaire.encode("utf-8"))
    for cle, contenu in plan.images.items():
        chemin = corpus / cle
        if not chemin.is_file() or chemin.read_bytes() != contenu:
            ecrire(chemin, contenu)
    if supprimer:
        for cle in plan.pages_obsoletes + plan.images_obsoletes:
            chemin = corpus / cle
            chemin.unlink(missing_ok=True)
            parent = chemin.parent
            while parent != corpus and parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent
    ecrire(corpus / "manifest.json", (json.dumps(plan.manifeste, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


# -- interface ----------------------------------------------------------------

def liste(titre: str, noms: list[str], limite: int = 12) -> None:
    if not noms:
        return
    print("  {} ({}) :".format(titre, len(noms)))
    for nom in noms[:limite]:
        print("    - {}".format(nom))
    if len(noms) > limite:
        print("    ... et {} autre(s)".format(len(noms) - limite))


def rappels(corpus: Path, plan: Plan) -> list[str]:
    """Ce qui reste à relire à la main après l'intégration."""
    manifeste = plan.manifeste
    messages = []
    lisezmoi = corpus / "README.md"
    if lisezmoi.is_file():
        texte = lire(lisezmoi)
        for decompte, motif, nom in COMPTES_README:
            trouve = re.search(r"\|\s*" + motif + r"\s*\|\s*(\d+)\s*\|", texte)
            if trouve and int(trouve.group(1)) != manifeste[decompte]:
                messages.append("README.md du corpus : le tableau de provenance indique {} {}, la collecte en compte {}".format(
                    trouve.group(1), nom, manifeste[decompte]))
        messages.append("README.md du corpus : verifier la date de collecte du tableau de provenance ({})".format(
            manifeste["retrieved_at"][:10]))
    messages.append("README de section : relire ceux dont les sections officielles ont change")
    return messages


def main(argv: list[str] | None = None) -> int:
    for flux in (sys.stdout, sys.stderr):
        reconfigurer = getattr(flux, "reconfigure", None)
        if reconfigurer is not None:
            reconfigurer(errors="replace")

    parseur = argparse.ArgumentParser(
        description="Integre une collecte du site ROMEO dans le corpus versionne",
        epilog="Sans --write, rien n'est ecrit : l'outil compare et rend 1 s'il y a des ecarts.",
    )
    parseur.add_argument("collecte", type=Path, help="dossier produit par romeo_doc_scraper.py")
    parseur.add_argument("--corpus", type=Path, default=CORPUS, help="corpus a mettre a jour (defaut : {})".format(CORPUS))
    parseur.add_argument("--write", action="store_true", help="ecrire dans le corpus puis le verifier")
    parseur.add_argument("--prune", action="store_true",
                         help="supprimer les pages et images disparues du site (exige --write)")
    args = parseur.parse_args(argv)
    if args.prune and not args.write:
        parseur.error("--prune exige --write")

    try:
        plan = preparer(args.collecte, args.corpus)
    except ErreurFusion as erreur:
        print("collecte refusee : {}".format(erreur))
        return 2

    ecarts = comparer(plan, args.corpus)
    manifeste = plan.manifeste
    print("Collecte : {} ({} pages, {} images, relevee le {})".format(
        args.collecte, manifeste["pages"], manifeste["images"], manifeste["retrieved_at"]))
    print("Corpus   : {}".format(args.corpus))
    liste("pages nouvelles", ecarts.pages_nouvelles)
    liste("pages modifiees (hors scraped_at)", ecarts.pages_modifiees)
    liste("images nouvelles", ecarts.images_nouvelles)
    liste("images modifiees", ecarts.images_modifiees)
    liste("disparues du site", ecarts.obsoletes)
    if ecarts.sommaire:
        print("  SOMMAIRE.md : different")
    if ecarts.manifeste:
        print("  manifest.json : different (hors retrieved_at et empreintes)")
    if plan.reparations:
        print("  ancres reecrites : {}".format(
            ", ".join("{} ({})".format(cle, len(r)) for cle, r in sorted(plan.reparations.items()))))

    if not args.write:
        if ecarts.identique:
            print("Le corpus correspond a la collecte (dates de collecte ignorees).")
            return 0
        print("Ecarts releves : relancer avec --write pour integrer la collecte.")
        return 1

    if ecarts.obsoletes and not args.prune:
        print("Rien n'a ete ecrit : des fichiers ont disparu du site. Relire la liste, puis relancer avec --prune.")
        return 2
    appliquer(plan, args.corpus, supprimer=args.prune)
    print("Collecte integree : {} pages, SOMMAIRE.md et manifest.json ecrits.".format(len(plan.pages)))
    for message in rappels(args.corpus, plan):
        print("A reprendre a la main : {}".format(message))
    print()
    return verify_corpus.main(args.corpus)


if __name__ == "__main__":
    raise SystemExit(main())
