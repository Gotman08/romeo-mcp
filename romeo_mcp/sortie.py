"""Decoupage des sorties de commandes distantes en sections.

Le serveur groupe plusieurs commandes dans un seul aller-retour SSH et separe
leurs sorties par des marqueurs. Tant que les commandes produisent du texte
controle (`sinfo`, `sacct`, `find`), un marqueur simple suffit.

Ce n'est plus vrai des que la sortie contient du **texte utilisateur**. Un
journal de calcul contenant `### Validation ###` ou une banniere `##########`
cree alors des sections parasites, et le contenu qui suit est range dessous au
lieu d'etre rendu. Ce qui disparait est justement la fin du journal, c'est-a-dire
la trace d'erreur que l'on etait alle chercher.

D'ou le marqueur a jeton : un identifiant tire au hasard a chaque appel, que le
texte deja ecrit ne peut pas contenir. C'est la meme parade que le protocole a
sentinelles de :mod:`romeo_mcp.ssh`.
"""

from __future__ import annotations

import uuid


def nouveau_jeton() -> str:
    """Jeton court, unique a un appel."""
    return uuid.uuid4().hex[:12]


def marqueur(jeton: str, nom: str) -> str:
    """Marqueur de debut de section, impossible a imiter par hasard."""
    return "###{}#{}".format(jeton, nom.upper())


def decouper(
    texte: str,
    jeton: str,
    *,
    ignorer_vides: bool = False,
    rogner: bool = False,
) -> dict[str, list[str]]:
    """Repartit les lignes de `texte` selon les marqueurs portant `jeton`.

    Les lignes precedant le premier marqueur sont ignorees : ce sont les
    residus d'un shell de login. Les options reproduisent les variantes
    historiques des sites d'appel :

    ``ignorer_vides``
        ecarte les lignes blanches, pour les sorties tabulaires ou une ligne
        vide n'a pas de sens.
    ``rogner``
        supprime les espaces de bord, pour les sorties dont les colonnes sont
        alignees par du remplissage.

    Le texte utilisateur veut au contraire etre conserve tel quel : d'ou des
    valeurs par defaut qui ne touchent a rien.
    """
    prefixe = "###{}#".format(jeton)
    sections: dict[str, list[str]] = {}
    courante: list[str] | None = None

    for ligne in texte.splitlines():
        if ligne.startswith(prefixe):
            nom = ligne[len(prefixe):].strip().lower()
            courante = sections.setdefault(nom, [])
            continue
        if courante is None:
            continue
        if rogner:
            ligne = ligne.strip()
        if ignorer_vides and not ligne.strip():
            continue
        courante.append(ligne)

    return sections


def premiere_ligne(sections: dict[str, list[str]], nom: str, defaut: str = "") -> str:
    """Premiere ligne d'une section, ou `defaut`.

    Indispensable parce qu'une section peut exister et etre vide : le marqueur
    a ete emis mais la commande n'a rien produit. Un acces direct par index
    leverait alors une IndexError au milieu d'un outil.
    """
    lignes = sections.get(nom)
    return lignes[0] if lignes else defaut
