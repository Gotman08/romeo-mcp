"""Garde-fous : ce que le serveur refuse d'executer sur le noeud de login.

Deux risques distincts sont couverts.

1. **Abus du noeud de login.** Un modele qui lance une compilation ou un
   entrainement sur romeo1 degrade le cluster pour tout le monde et expose
   l'utilisateur a une sanction de l'administration. Le refus renvoie
   systematiquement vers l'outil approprie.

2. **Destruction accidentelle.** Un `rm -rf` mal cible sur un scratch partage
   n'est pas rattrapable. Les motifs manifestement destructeurs sont bloques.

Ce module ne pretend pas etre une sandbox : il rend les erreurs *frequentes*
difficiles, pas les malveillances impossibles.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Sequence

#: Binaires qui n'ont rien a faire sur un noeud de login.
HEAVY_COMMANDS = {
    "make": "build_on_node",
    "cmake": "build_on_node",
    "ninja": "build_on_node",
    "gcc": "build_on_node",
    "g++": "build_on_node",
    "cc": "build_on_node",
    "c++": "build_on_node",
    "gfortran": "build_on_node",
    "nvcc": "build_on_node",
    "nvc": "build_on_node",
    "nvfortran": "build_on_node",
    "cargo": "build_on_node",
    "rustc": "build_on_node",
    "go": "build_on_node",
    "mpirun": "job_prepare",
    "mpiexec": "job_prepare",
    # `srun` n'est volontairement PAS bloque : la documentation ROMEO le
    # presente comme la voie normale vers un noeud de calcul (`srun --pty bash`),
    # et c'est d'ailleurs ce que `build_on_node` execute depuis le login.
    "julia": "job_prepare",
    "matlab": "job_prepare",
    "Rscript": "job_prepare",
}

#: `pip install` compile des roues natives : c'est le piege d'architecture.
_PIP_INSTALL = re.compile(r"^(pip|pip3|python3?\s+-m\s+pip)\b.*\binstall\b")

#: Motifs destructeurs refuses quel que soit le contexte.
_DESTRUCTIVE = [
    (re.compile(r"\brm\b[^|;&]*\s-[a-zA-Z]*[rR][a-zA-Z]*\s+(/|~|\$HOME)\s*$"),
     "suppression recursive d'une racine"),
    (re.compile(r"\bmkfs(\.|\b)"), "formatage de systeme de fichiers"),
    (re.compile(r"\bdd\b[^|;&]*\bof=/dev/"), "ecriture directe sur un peripherique"),
    (re.compile(r"\bshred\b"), "effacement irreversible"),
    (re.compile(r":\s*\(\s*\)\s*\{.*\|.*&\s*\}"), "fork bomb"),
    (re.compile(r"\bchmod\b[^|;&]*\s-[a-zA-Z]*R[a-zA-Z]*\s+777\s+(/|~|\$HOME)"),
     "ouverture recursive des permissions"),
    (re.compile(r">\s*/dev/(sd|nvme|vd)"), "ecriture sur un disque brut"),
]

def allowed_roots(
    home: str, scratch: str, extra: Sequence[str] = ()
) -> list[str]:
    """Racines accessibles par les outils fichiers.

    `/project/<code>` est l'espace projet officiel de ROMEO 2025 ; `/gpfs/projet`
    existe egalement sur le cluster et reste accepte. `/apps` heberge les
    installations systeme et les environnements Spack : sa lecture est utile,
    son ecriture est de toute facon refusee par les permissions.

    `extra` recoit les alias reels du scratch. Sur ROMEO, `/scratch_p/<user>`
    est un lien vers un chemin physique GPFS : un modele qui relit un script
    existant y trouve la forme physique, et la refuser serait absurde puisque
    les deux designent le meme repertoire. Ces alias sont **decouverts** par la
    session, jamais supposes, et restent portee par utilisateur : ajouter
    `/gpfs/scratch` en entier ouvrirait le scratch des autres.
    """
    roots = [home, scratch, "/project", "/gpfs/projet", "/apps", "/tmp"]
    for alias in extra:
        candidat = (alias or "").strip()
        if candidat.startswith("/") and candidat not in roots:
            roots.append(posixpath.normpath(candidat))
    return roots


class GuardError(PermissionError):
    """Commande ou chemin refuse. Le message explique l'alternative."""


_SEPARATORS = re.compile(r"\|\||&&|[;|&\n]")
_ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _segments(command: str) -> list[str]:
    """Decoupe une ligne de commande en segments executables."""
    return [seg.strip() for seg in _SEPARATORS.split(command) if seg.strip()]


def _head(segment: str) -> str:
    """Premier mot reellement executable d'un segment (hors affectations env)."""
    for word in segment.split():
        if _ENV_ASSIGN.match(word):
            continue
        return word.split("/")[-1]
    return ""


def check_login_command(command: str, allow_heavy: bool = False) -> None:
    """Refuse une commande inadaptee au noeud de login.

    Leve :class:`GuardError` avec l'outil de remplacement a utiliser.

    ``allow_heavy`` leve le refus des compilations et installations. La
    documentation ROMEO autorise explicitement les builds Spack et les
    ``python -m pip install`` en environnement virtuel **a destination du
    x86_64** depuis le noeud de login ; elle ne l'interdit que pour aarch64.
    Ce drapeau existe pour ce cas precis et exige une intention deliberee : les
    verifications destructrices, elles, restent toujours actives.
    """
    text = (command or "").strip()
    if not text:
        raise GuardError("commande vide")

    for pattern, label in _DESTRUCTIVE:
        if pattern.search(text):
            raise GuardError(
                "commande refusee ({}). Si l'intention est legitime, execute-la "
                "toi-meme depuis un terminal : le serveur MCP ne pratique pas "
                "les operations irreversibles.".format(label)
            )

    if len(text) > 4_000:
        raise GuardError(
            "commande trop longue pour le noeud de login. Un script de cette "
            "taille doit etre soumis via `job_prepare`."
        )

    if allow_heavy:
        return

    for segment in _segments(text):
        head = _head(segment)

        if head in HEAVY_COMMANDS:
            tool = HEAVY_COMMANDS[head]
            raise GuardError(
                "`{}` est interdit sur le noeud de login : c'est une machine "
                "partagee reservee a la preparation des jobs. Utilise l'outil "
                "`{}`.".format(head, tool)
            )

        if _PIP_INSTALL.match(segment):
            raise GuardError(
                "`pip install` sur le noeud de login produit des roues x86_64, "
                "inutilisables sur les noeuds GPU aarch64. Si la cible est "
                "aarch64, utilise `build_on_node(arch='armgpu', ...)`. Si tu "
                "vises bien le x86_64, la documentation ROMEO autorise la "
                "procedure officielle (romeo_load_x64cpu_env, spack load, "
                "python -m venv, puis pip) depuis le login : relance alors avec "
                "allow_heavy=true."
            )

        # Un interpreteur avec un fichier de script en argument : calcul probable.
        if head in ("python", "python3") and re.search(r"\S+\.py\b", segment):
            raise GuardError(
                "executer un script Python sur le noeud de login est interdit. "
                "Passe par `job_prepare`. Les formes courtes `python -c` et "
                "`python --version` restent autorisees pour l'inspection."
            )

    if len(text) > 4_000:
        raise GuardError(
            "commande trop longue pour le noeud de login. Un script de cette "
            "taille doit etre soumis via `job_prepare`."
        )


def check_path(
    path: str, home: str, scratch: str, extra_roots: Sequence[str] = ()
) -> str:
    """Normalise un chemin distant et verifie qu'il reste dans une racine permise."""
    if not path or not path.strip():
        raise GuardError("chemin vide")

    raw = path.strip()
    if raw.startswith("~"):
        raw = home + raw[1:]
    if not raw.startswith("/"):
        raw = posixpath.join(scratch, raw)

    resolved = posixpath.normpath(raw)
    if "\x00" in resolved:
        raise GuardError("chemin invalide")

    roots = allowed_roots(home, scratch, extra_roots)
    for root in roots:
        if resolved == root or resolved.startswith(root.rstrip("/") + "/"):
            return resolved

    raise GuardError(
        "chemin hors perimetre : {}. Racines autorisees : {}.".format(
            resolved, ", ".join(roots)
        )
    )
