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
from dataclasses import dataclass

#: Binaires qui n'ont rien a faire sur un noeud de login.
HEAVY_COMMANDS = {
    "make": "compute_command_prepare",
    "cmake": "compute_command_prepare",
    "ninja": "compute_command_prepare",
    "gcc": "compute_command_prepare",
    "g++": "compute_command_prepare",
    "cc": "compute_command_prepare",
    "c++": "compute_command_prepare",
    "gfortran": "compute_command_prepare",
    "nvcc": "compute_command_prepare",
    "nvc": "compute_command_prepare",
    "nvfortran": "compute_command_prepare",
    "cargo": "compute_command_prepare",
    "rustc": "compute_command_prepare",
    "go": "compute_command_prepare",
    "mpirun": "job_prepare",
    "mpiexec": "job_prepare",
    # `srun` n'est volontairement PAS bloque : la documentation ROMEO le
    # presente comme la voie normale vers un noeud de calcul (`srun --pty bash`),
    # et c'est d'ailleurs ce que `compute_command_prepare` execute depuis le login.
    "julia": "job_prepare",
    "matlab": "job_prepare",
    "Rscript": "job_prepare",
    "dd": "job_prepare",
}

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
        candidat = alias or ""
        if candidat.startswith("/") and candidat not in roots:
            roots.append(posixpath.normpath(candidat))
    return roots


class GuardError(PermissionError):
    """Commande ou chemin refuse. Le message explique l'alternative."""


_ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_PYTHON = re.compile(r"python(?:[23](?:\.\d+)*)?$")
_PIP = re.compile(r"pip(?:[23](?:\.\d+)*)?$")
_CONTROL = {"if", "then", "elif", "else", "fi", "while", "until", "for", "select",
            "do", "done", "case", "esac", "function", "!", "coproc"}


def _ambiguous() -> None:
    raise GuardError("syntaxe shell dynamique ou enveloppe non prise en charge sur le login. "
                     "Utilise une commande d'inspection simple ou `compute_command_prepare`.")


def _destructive(label: str) -> None:
    raise GuardError("commande refusee ({}). Si l'intention est legitime, execute-la "
                     "toi-meme depuis un terminal : le serveur MCP ne pratique pas "
                     "les operations irreversibles.".format(label))


@dataclass(frozen=True)
class _Token:
    value: str
    operator: bool = False
    dynamic: bool = False


def _tokens(text: str) -> list[_Token]:
    """Lexeur du sous-ensemble accepte ; les operateurs cites restent du texte.

    Ni eval, substitutions ni constructions composees ne sont interpretes.
    Les syntaxes que cette analyse ne peut prouver sont refusees explicitement.
    """
    tokens, word = [], []
    active, dynamic, quote, index = False, False, "", 0
    def flush():
        nonlocal active, dynamic
        if active:
            tokens.append(_Token("".join(word), dynamic=dynamic))
            word.clear()
            active, dynamic = False, False
    while index < len(text):
        char = text[index]
        if quote == "'":
            if char == "'":
                quote = ""
            else:
                word.append(char)
        elif char == "\\" and quote != "'":
            index += 1
            if index == len(text):
                _ambiguous()
            following = text[index]
            if quote == '"' and following not in '$`"\\\n':
                word.append("\\")
            if following != "\n":
                word.append(following)
                active = True
        elif quote == '"' and char == '"':
            quote = ""
        elif not quote and char in "'\"":
            quote, active = char, True
        elif not quote and char in " \t\r":
            flush()
        elif not quote and char == "#" and not active:
            while index < len(text) and text[index] != "\n":
                index += 1
            if index < len(text):
                tokens.append(_Token("\n", operator=True))
        elif not quote and char in ";|&<>(){}\n":
            flush()
            operator = char
            for candidate in ("&>>", "<<<", "<<-", "&&", "||", "|&", "&>", ">>", "<<", ">&", "<&"):
                if text.startswith(candidate, index):
                    operator = candidate
                    break
            tokens.append(_Token(operator, operator=True))
            index += len(operator) - 1
        else:
            if char == "`" or (char == "$" and text[index + 1:index + 2] in {"(", "{"}):
                _ambiguous()
            dynamic = dynamic or char == "$"
            active = True
            word.append(char)
        index += 1
    if quote:
        _ambiguous()
    flush()
    return tokens


def _commands(text: str, depth: int = 0) -> list[list[_Token]]:
    if depth > 8:
        _ambiguous()
    segments, words = [], []
    tokens = _tokens(text)
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if not token.operator:
            words.append(token)
        elif token.value in {";", "|", "||", "&&", "&", "|&", "\n"}:
            if words:
                segments.append(words)
                words = []
        elif token.value in {">", ">>", "<", ">&", "<&", "&>", "&>>"}:
            index += 1
            if index == len(tokens) or tokens[index].operator:
                _ambiguous()
            target = tokens[index]
            if target.dynamic:
                _ambiguous()
            if token.value != "<" and re.match(r"/dev/(?:sd|nvme|vd)", target.value):
                _destructive("ecriture sur un disque brut")
            if words and words[-1].value.isdecimal():
                words.pop()  # descripteur de fichier, pas un argument executable
        else:
            _ambiguous()  # here-doc, sous-shell, fonction, substitution de processus
        index += 1
    if words:
        segments.append(words)
    result = []
    for segment in segments:
        result.extend(_unwrap(segment, depth))
    return result


def _options(words: list[_Token], flags: set[str], values: set[str]) -> list[_Token]:
    """Retire uniquement les options d'enveloppe dont l'arite est connue."""
    index = 0
    while index < len(words) and words[index].value.startswith("-"):
        value = words[index].value
        if value == "--":
            return words[index + 1:]
        if value in {"--help", "--version"}:
            return []
        if value in flags:
            index += 1
        elif value in values:
            if index + 1 >= len(words):
                _ambiguous()
            index += 2
        elif any(value.startswith(option + "=") for option in values if option.startswith("--")):
            index += 1
        elif any(value.startswith(option) and len(value) > len(option) for option in values if len(option) == 2):
            index += 1
        else:
            _ambiguous()
    return words[index:]


def _unwrap(words: list[_Token], depth: int) -> list[list[_Token]]:
    for _ in range(16):
        while words and _ENV_ASSIGN.match(words[0].value):
            words = words[1:]
        if not words:
            return []
        if words[0].dynamic:
            _ambiguous()
        head = posixpath.basename(words[0].value)
        args = words[1:]
        if head in _CONTROL or head in {"eval", "source", ".", "xargs", "parallel", "watch"}:
            _ambiguous()
        if head == "find" and any(arg.value in {"-exec", "-execdir", "-ok", "-okdir"} for arg in args):
            _ambiguous()
        if head in {"bash", "sh", "dash", "ksh", "zsh"}:
            index = 0
            while index < len(args):
                value = args[index].value
                if value == "--version":
                    return []
                if value in {"--noprofile", "--norc"}:
                    index += 1
                    continue
                if value.startswith("-") and not value.startswith("--") and set(value[1:]) <= set("cl") and "c" in value:
                    if index + 1 >= len(args) or args[index + 1].dynamic:
                        _ambiguous()
                    return _commands(args[index + 1].value, depth + 1)
                _ambiguous()
            _ambiguous()  # script opaque ou shell interactif
        elif head == "env":
            words = _options(args, {"-i", "--ignore-environment", "-0", "--null"},
                             {"-u", "--unset", "-C", "--chdir"})
        elif head in {"command", "builtin"}:
            if args and args[0].value in {"-v", "-V"}:
                return []  # recherche du binaire, sans execution
            words = _options(args, {"-p"}, set())
        elif head == "timeout":
            words = _options(args, {"--foreground", "--preserve-status", "-v", "--verbose"},
                             {"-k", "--kill-after", "-s", "--signal"})
            if not words or not re.fullmatch(r"\d+(?:\.\d+)?[smhd]?", words[0].value):
                _ambiguous()
            words = words[1:]
        elif head == "nice":
            if args and re.fullmatch(r"-[+-]?\d+", args[0].value):
                args = args[1:]
            words = _options(args, set(), {"-n", "--adjustment"})
        elif head == "sudo":
            words = _options(args, {"-n", "-E", "-H", "-S", "-b", "-P", "--non-interactive", "--set-home"},
                             {"-u", "-g", "-h", "-p", "-C", "-T", "-r", "-t", "--user", "--group"})
        elif head == "exec":
            words = _options(args, {"-c", "-l", "-cl", "-lc"}, {"-a"})
        elif head == "nohup":
            words = _options(args, set(), set())
        elif head == "stdbuf":
            words = _options(args, set(), {"-i", "-o", "-e", "--input", "--output", "--error"})
        elif head == "setsid":
            words = _options(args, {"-c", "-f", "-w", "--ctty", "--fork", "--wait"}, set())
        elif head == "time":
            words = _options(args, {"-p", "-v", "-a", "-q", "--portability", "--verbose", "--append", "--quiet"},
                             {"-f", "-o", "--format", "--output"})
        else:
            return [words]
    _ambiguous()


def _root_target(token: _Token) -> bool:
    value = token.value
    if token.dynamic:
        # Impossible de prouver la cible d'une suppression recursive variable.
        return True
    return (posixpath.normpath(value) in {"/", "//"} or value in {"/*", "/.*"}
            or re.fullmatch(r"~[^/]*(?:/|/\.)?", value) is not None)


def _check_destructive(head: str, args: list[_Token]) -> None:
    values = [arg.value for arg in args]
    recursive, operands, options = False, [], True
    for arg in args:
        value = arg.value
        if options and value == "--":
            options = False
        elif options and value.startswith("-"):
            recursive |= value == "--recursive" or (not value.startswith("--") and any(c in value for c in "rR"))
        else:
            operands.append(arg)
    if head == "rm" and recursive and any(_root_target(arg) for arg in operands):
        _destructive("suppression recursive d'une racine")
    if head == "mkfs" or head.startswith("mkfs."):
        _destructive("formatage de systeme de fichiers")
    if head == "shred":
        _destructive("effacement irreversible")
    if head == "dd" and any(value.startswith("of=/dev/") for value in values):
        _destructive("ecriture directe sur un peripherique")
    if head == "dd" and any(arg.dynamic and arg.value.startswith("of=") for arg in args):
        _ambiguous()
    if head == "chmod" and recursive and "777" in values and any(_root_target(arg) for arg in operands):
        _destructive("ouverture recursive des permissions")


def _python_mode(values: list[str]) -> tuple[bool, list[str]]:
    """Retourne (inspection, arguments pip), avant les arguments du script.

    Un -c APRES train.py appartient au script et ne doit pas lever le refus.
    """
    index = 0
    while index < len(values):
        value = values[index]
        if value == "-m":
            module = values[index + 1:index + 2]
            return (module in (["pip"], ["pip3"]), values[index + 2:] if module in (["pip"], ["pip3"]) else [])
        if value == "-c" or value.startswith("-c"):
            return True, []
        if value in {"--version", "--help"}:
            return True, []
        if value in {"-W", "-X"}:
            index += 2
            continue
        if value.startswith("-W") or value.startswith("-X"):
            index += 1
            continue
        if value.startswith("-") and value != "--" and set(value[1:]) <= set("bBdEhiIOPqRsSuvVx"):
            index += 1
            continue
        return False, []
    return True, []


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

    if len(text) > 4_000:
        raise GuardError(
            "commande trop longue pour le noeud de login. Un script de cette "
            "taille doit etre soumis via `job_prepare`."
        )

    for words in _commands(text):
        head = posixpath.basename(words[0].value)
        args = words[1:]
        _check_destructive(head, args)
        if allow_heavy:
            continue

        if head in HEAVY_COMMANDS:
            tool = HEAVY_COMMANDS[head]
            raise GuardError(
                "`{}` est interdit sur le noeud de login : c'est une machine "
                "partagee reservee a la preparation des jobs. Utilise l'outil "
                "`{}`.".format(head, tool)
            )

        values = [arg.value for arg in args]
        python = _PYTHON.fullmatch(head)
        inspection, pip_values = _python_mode(values) if python else (False, [])
        if (_PIP.fullmatch(head) and "install" in values) or (python and "install" in pip_values):
            raise GuardError(
                "`pip install` sur le noeud de login produit des roues x86_64, "
                "inutilisables sur les noeuds GPU aarch64. Si la cible est "
                "aarch64, utilise `compute_command_prepare(arch='armgpu', ...)`. Si tu "
                "vises bien le x86_64, la documentation ROMEO autorise la "
                "procedure officielle (romeo_load_x64cpu_env, spack load, "
                "python -m venv, puis pip) depuis le login : relance alors avec "
                "allow_heavy=true."
            )

        # Un interpreteur avec un fichier de script en argument : calcul probable.
        if python and not inspection:
            raise GuardError(
                "executer un script Python sur le noeud de login est interdit. "
                "Passe par `job_prepare`. Les formes courtes `python -c` et "
                "`python --version` restent autorisees pour l'inspection."
            )

def check_path(
    path: str, home: str, scratch: str, extra_roots: Sequence[str] = ()
) -> str:
    """Valide le chemin litteral ; les sondes distantes confinent aussi sa cible physique."""
    if not path:
        raise GuardError("chemin vide")
    if len(path) > 4096 or "\x00" in path:
        raise GuardError("chemin invalide ou trop long (maximum 4096 caracteres)")
    try:
        path.encode('utf-8')
    except UnicodeError:
        raise GuardError('chemin UTF-8 invalide') from None

    raw = path
    if raw == "~" or raw.startswith("~/"):
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
