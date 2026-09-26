"""Outillage partage par les suites de tests.

Trois besoins, jusqu'ici recopies dans chaque suite avec des variantes :
le compteur d'echecs, la fonction d'assertion, et la mise en place du chemin
d'import. Cette derniere etait fragile : `sys.path.insert(0, ".")` suppose que
la suite est lancee depuis la racine du depot, et echoue silencieusement
autrement. Le chemin est desormais derive du fichier lui-meme.
"""

from __future__ import annotations

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]

# La racine du depot d'abord (pour `romeo_mcp`), puis le dossier des tests
# (pour ce module et ses voisins), independamment du repertoire courant.
for _chemin in (str(RACINE), str(RACINE / "tests")):
    if _chemin not in sys.path:
        sys.path.insert(0, _chemin)

#: Libelles des assertions qui ont echoue, dans l'ordre de rencontre.
ECHECS: list[str] = []


def check(label: str, condition, detail: object = "") -> bool:
    """Verifie une condition et journalise le resultat.

    Rend le booleen evalue, ce qui permet d'enchainer une verification
    dependante sans repeter la condition.
    """
    reussi = bool(condition)
    if reussi:
        print("  OK   {}".format(label))
    else:
        print("  ECHEC {}{}".format(label, "  -> {}".format(detail) if detail else ""))
        ECHECS.append(label)
    return reussi


def expect_error(label: str, fn, needle: str = "", exceptions=Exception) -> bool:
    """Verifie qu'un appel echoue, et que son message contient `needle`.

    Un refus qui survient pour la mauvaise raison est un faux positif : c'est
    pourquoi le message est controle et pas seulement la levee.
    """
    try:
        fn()
    except exceptions as exc:  # noqa: BLE001 - le type attendu est passe par l'appelant
        if needle and needle.lower() not in str(exc).lower():
            return check(label, False, "message inattendu : {}".format(exc))
        return check(label, True)
    return check(label, False, "aucune erreur levee")


def section(titre: str) -> None:
    """Titre de groupe, pour rendre la sortie lisible."""
    print("\n-- {} --".format(titre))


def bilan(titre: str) -> int:
    """Affiche le verdict et rend le code de sortie du processus."""
    print()
    if ECHECS:
        print("{} : {} ECHEC(S) -> {}".format(titre, len(ECHECS), ECHECS))
        return 1
    print("{} : TOUT PASSE".format(titre))
    return 0
