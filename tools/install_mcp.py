#!/usr/bin/env python3
"""Installe (ou retire) le serveur MCP ROMEO dans les clients qui le supportent.

Cibles prises en charge :

- **claude-code**    : Claude Code en ligne de commande, via `claude mcp add`,
                       avec repli sur `~/.claude.json` si le binaire est absent.
- **claude-desktop** : l'application Claude, via `claude_desktop_config.json`.
- **codex**          : Codex (application et CLI partagent `config.toml`).

Chaque emplacement dépend du système, et parfois de la machine : rien n'est
codé en dur. Les chemins sont dérivés de la plateforme courante, des variables
d'environnement (`APPDATA`, `XDG_CONFIG_HOME`, `CODEX_HOME`) et, sous WSL, du
profil Windows monté sous `/mnt`, car l'application Claude ou Codex tourne
alors côté Windows tandis que le script s'exécute côté Linux.

Le script est idempotent : réexécuté, il met à jour l'entrée existante au lieu
de la dupliquer. Toute configuration modifiée est sauvegardée au préalable.

Exemples :
    python tools/install_mcp.py --list
    python tools/install_mcp.py                       # toutes les cibles détectées
    python tools/install_mcp.py --targets codex --dry-run
    python tools/install_mcp.py --uninstall
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - dépend de la version
    tomllib = None

CIBLES = ("claude-code", "claude-desktop", "codex")
NOM_DEFAUT = "romeo"


# =============================================================================
# Découverte de l'environnement
# =============================================================================
def racine_projet() -> Path:
    """Racine du dépôt, déduite de l'emplacement de ce script."""
    return Path(__file__).resolve().parent.parent


def sous_wsl() -> bool:
    """Vrai si l'on tourne dans WSL, où les applications sont côté Windows."""
    if sys.platform != "linux":
        return False
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


def existe(chemin: Path) -> bool:
    """`Path.exists()` tolérant aux lecteurs montés mais inaccessibles.

    Sous WSL, `/mnt/` peut contenir des points de montage morts (lecteur réseau
    déconnecté, unité amovible retirée) dont l'interrogation lève une erreur.
    """
    try:
        return chemin.exists()
    except OSError:
        return False


def profils_windows() -> list[Path]:
    """Profils utilisateur Windows visibles depuis WSL."""
    if not sous_wsl():
        return []
    profils = []
    try:
        lecteurs = list(Path("/mnt").glob("*"))
    except OSError:
        return []
    for lecteur in lecteurs:
        base = lecteur / "Users"
        try:
            if not base.is_dir():
                continue
            entrees = list(base.iterdir())
        except OSError:
            continue
        for profil in entrees:
            try:
                interessant = profil.is_dir()
            except OSError:
                continue
            if interessant and profil.name not in (
                "Public", "Default", "Default User", "All Users"
            ):
                profils.append(profil)
    return profils


def cible_windows(config: Path) -> bool:
    """Vrai si ce fichier de configuration appartient au monde Windows.

    Depuis WSL, l'application Claude ou Codex tourne côté Windows : elle ne sait
    pas lire un chemin `/mnt/c/...`. Les chemins écrits dans sa configuration
    doivent donc être traduits en forme Windows.
    """
    return sous_wsl() and str(config).startswith("/mnt/")


def vers_forme_windows(chemin: str) -> str:
    """Traduit un chemin WSL en chemin Windows, via `wslpath`."""
    if not chemin.startswith("/"):
        return chemin
    try:
        proc = subprocess.run(
            ["wslpath", "-w", chemin],
            capture_output=True, text=True, timeout=20,
            encoding="utf-8", errors="replace",
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return chemin


def adapter(conf: dict, config: Path) -> dict:
    """Adapte une configuration aux conventions de chemin du client visé."""
    if not cible_windows(config):
        return conf
    adaptee = dict(conf)
    adaptee["command"] = vers_forme_windows(conf["command"])
    if conf.get("env"):
        adaptee["env"] = {
            cle: vers_forme_windows(valeur) if str(valeur).startswith("/") else valeur
            for cle, valeur in conf["env"].items()
        }
    return adaptee


def interpreteur(racine: Path, override: str | None) -> Path:
    """Interpréteur Python à faire lancer par le client.

    Le venv n'a pas la même disposition selon la plateforme : `Scripts` sous
    Windows, `bin` ailleurs. On privilégie celui qui correspond au système
    courant, faute de quoi le client lancerait un binaire inexécutable.
    """
    if override:
        chemin = Path(override).expanduser().resolve()
        if not chemin.exists():
            raise SystemExit("interpréteur introuvable : {}".format(chemin))
        return chemin

    windows = racine / ".venv" / "Scripts" / "python.exe"
    posix = racine / ".venv" / "bin" / "python"
    ordre = [windows, posix] if sys.platform == "win32" else [posix, windows]
    for candidat in ordre:
        if candidat.exists():
            return candidat
    return Path(sys.executable)


def dossier_docs(racine: Path) -> Path | None:
    """Meme resolution que le serveur, independante du dossier courant."""
    depuis_env = os.environ.get("ROMEO_DOCS_DIR")
    candidat = Path(depuis_env).expanduser() if depuis_env else racine / "romeo_mcp" / "documentation"
    if not candidat.is_absolute():
        candidat = racine / candidat
    return candidat.resolve() if candidat.is_dir() else None


# =============================================================================
# Emplacements des configurations, par système
# =============================================================================
def candidats_claude_desktop() -> list[Path]:
    home = Path.home()
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else home / "AppData" / "Roaming"
        return [base / "Claude" / "claude_desktop_config.json"]

    if sys.platform == "darwin":
        return [
            home / "Library" / "Application Support" / "Claude"
            / "claude_desktop_config.json"
        ]

    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else home / ".config"
    chemins = [base / "Claude" / "claude_desktop_config.json"]
    # Sous WSL, l'application est installée côté Windows.
    chemins += [
        profil / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json"
        for profil in profils_windows()
    ]
    return chemins


def candidats_codex() -> list[Path]:
    chemins = []
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        chemins.append(Path(codex_home) / "config.toml")
    chemins.append(Path.home() / ".codex" / "config.toml")
    chemins += [profil / ".codex" / "config.toml" for profil in profils_windows()]
    return chemins


def premier_existant(chemins: list[Path]) -> Path | None:
    for chemin in chemins:
        if existe(chemin):
            return chemin
    return None


# =============================================================================
# Résultats
# =============================================================================
@dataclass
class Resultat:
    cible: str
    statut: str  # installe | desinstalle | inchange | absent | erreur | simule
    detail: str

    SYMBOLES = {
        "installe": "[+]",
        "desinstalle": "[-]",
        "inchange": "[=]",
        "simule": "[~]",
        "absent": "[ ]",
        "erreur": "[!]",
    }

    def ligne(self) -> str:
        return "{} {:<16} {}".format(
            self.SYMBOLES.get(self.statut, "[?]"), self.cible, self.detail
        )


def sauvegarder(chemin: Path) -> Path:
    """Copie horodatée avant toute modification."""
    copie = chemin.with_suffix(
        chemin.suffix + ".bak-{}".format(time.strftime("%Y%m%d-%H%M%S"))
    )
    shutil.copy2(chemin, copie)
    return copie


# =============================================================================
# Claude Desktop : JSON
# =============================================================================
def installer_claude_desktop(conf: dict, args) -> Resultat:
    chemin = Path(args.claude_desktop_config) if args.claude_desktop_config else (
        premier_existant(candidats_claude_desktop())
    )
    if chemin is None and "claude-desktop" in args.targets.split(",") and not args.uninstall:
        chemin = candidats_claude_desktop()[0]
    if chemin is None:
        essais = ", ".join(str(c) for c in candidats_claude_desktop())
        return Resultat(
            "claude-desktop", "absent",
            "configuration introuvable (cherché : {})".format(essais),
        )

    try:
        contenu = json.loads(chemin.read_text(encoding="utf-8")) if chemin.stat().st_size else {}
    except FileNotFoundError:
        contenu = {}
    except (OSError, json.JSONDecodeError) as exc:
        return Resultat("claude-desktop", "erreur", "{} illisible : {}".format(chemin, exc))

    conf = adapter(conf, chemin)
    serveurs = contenu.setdefault("mcpServers", {})
    if args.uninstall:
        if args.name not in serveurs:
            return Resultat("claude-desktop", "inchange", "{} : absent".format(chemin))
        if args.dry_run:
            return Resultat("claude-desktop", "simule", "retirerait {} de {}".format(args.name, chemin))
        del serveurs[args.name]
        sauvegarder(chemin)
        chemin.write_text(json.dumps(contenu, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return Resultat("claude-desktop", "desinstalle", str(chemin))

    if serveurs.get(args.name) == conf:
        return Resultat("claude-desktop", "inchange", "{} : déjà à jour".format(chemin))
    if args.dry_run:
        return Resultat("claude-desktop", "simule", "écrirait {} dans {}".format(args.name, chemin))

    serveurs[args.name] = conf
    chemin.parent.mkdir(parents=True, exist_ok=True)
    copie = sauvegarder(chemin) if chemin.exists() else None
    chemin.write_text(json.dumps(contenu, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return Resultat(
        "claude-desktop", "installe",
        "{} ({})".format(chemin, "sauvegarde : " + copie.name if copie else "creation"),
    )


# =============================================================================
# Codex : TOML
# =============================================================================
def toml_chaine(valeur: str) -> str:
    """Rend une chaîne TOML sûre pour un chemin Windows.

    Les chaînes littérales (guillemets simples) n'interprètent pas les
    antislashs : c'est la forme adaptée à `C:\\Users\\...`. On ne bascule sur
    une chaîne de base que si la valeur contient elle-même une apostrophe.
    """
    if "'" not in valeur:
        return "'{}'".format(valeur)
    return json.dumps(valeur)


def bloc_codex(nom: str, commande: str, arguments: list[str], env: dict) -> str:
    lignes = [
        "[mcp_servers.{}]".format(nom),
        "command = {}".format(toml_chaine(commande)),
        "args = [{}]".format(", ".join(toml_chaine(a) for a in arguments)),
        "startup_timeout_sec = 60",
    ]
    if env:
        lignes += ["", "[mcp_servers.{}.env]".format(nom)]
        lignes += ["{} = {}".format(cle, toml_chaine(val)) for cle, val in env.items()]
    return "\n".join(lignes) + "\n"


def remplacer_section_toml(texte: str, nom: str, bloc: str | None) -> tuple[str, bool]:
    """Remplace, insère ou supprime la section `[mcp_servers.<nom>]`.

    L'édition est textuelle et non un aller-retour de sérialisation : cela
    préserve intégralement le reste du fichier, commentaires et mise en forme
    compris, ce qu'un réécriture complète détruirait.
    """
    entete = "[mcp_servers.{}]".format(nom)
    prefixe_sous_table = "[mcp_servers.{}.".format(nom)

    lignes = texte.splitlines()
    sortie: list[str] = []
    index = 0
    trouve = False

    while index < len(lignes):
        nettoyee = lignes[index].strip()
        if nettoyee == entete or nettoyee.startswith(prefixe_sous_table):
            trouve = True
            index += 1
            # Absorber la section et ses sous-tables jusqu'au prochain en-tête
            # étranger.
            while index < len(lignes):
                suivante = lignes[index].strip()
                if suivante.startswith("[") and suivante != entete and not suivante.startswith(
                    prefixe_sous_table
                ):
                    break
                index += 1
            continue
        sortie.append(lignes[index])
        index += 1

    resultat = "\n".join(sortie).rstrip("\n")
    if bloc is not None:
        resultat = (resultat + "\n\n" + bloc) if resultat else bloc
    return resultat.rstrip("\n") + "\n", trouve


def installer_codex(commande: str, arguments: list[str], env: dict, args) -> Resultat:
    chemin = Path(args.codex_config) if args.codex_config else premier_existant(
        candidats_codex()
    )
    if chemin is None and "codex" in args.targets.split(",") and not args.uninstall:
        chemin = candidats_codex()[0]
    if chemin is None:
        essais = ", ".join(str(c) for c in candidats_codex())
        return Resultat(
            "codex", "absent", "configuration introuvable (cherché : {})".format(essais)
        )

    try:
        texte = chemin.read_text(encoding="utf-8")
    except FileNotFoundError:
        texte = ""
    except OSError as exc:
        return Resultat("codex", "erreur", "{} illisible : {}".format(chemin, exc))

    if cible_windows(chemin):
        commande = vers_forme_windows(commande)
        env = {c: vers_forme_windows(v) if str(v).startswith('/') else v
               for c, v in env.items()}
    bloc = None if args.uninstall else bloc_codex(args.name, commande, arguments, env)
    nouveau, trouve = remplacer_section_toml(texte, args.name, bloc)

    if args.uninstall and not trouve:
        return Resultat("codex", "inchange", "{} : absent".format(chemin))
    if nouveau == texte:
        return Resultat("codex", "inchange", "{} : déjà à jour".format(chemin))
    if args.dry_run:
        action = "retirerait" if args.uninstall else "écrirait"
        return Resultat("codex", "simule", "{} {} dans {}".format(action, args.name, chemin))

    # Ne jamais livrer un TOML cassé : on valide avant d'écrire.
    if tomllib is not None:
        try:
            tomllib.loads(nouveau)
        except Exception as exc:  # noqa: BLE001
            return Resultat("codex", "erreur", "TOML produit invalide : {}".format(exc))

    chemin.parent.mkdir(parents=True, exist_ok=True)
    copie = sauvegarder(chemin) if chemin.exists() else None
    chemin.write_text(nouveau, encoding="utf-8")
    statut = "desinstalle" if args.uninstall else "installe"
    return Resultat("codex", statut, "{} ({})".format(chemin, "sauvegarde : " + copie.name if copie else "creation"))


# =============================================================================
# Claude Code : CLI, avec repli fichier
# =============================================================================
def installer_claude_code(conf: dict, commande: str, arguments: list[str], args) -> Resultat:
    binaire = shutil.which("claude")
    if binaire:
        # État courant, pour ne pas annoncer une installation là où il n'y a
        # rien à changer.
        actuel = subprocess.run(
            [binaire, "mcp", "get", args.name],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        declare = actuel.returncode == 0
        identique = declare and commande in (actuel.stdout or "")

        if args.uninstall and not declare:
            return Resultat("claude-code", "inchange", "non déclaré")
        if not args.uninstall and identique:
            return Resultat("claude-code", "inchange",
                            "déjà déclaré (portée {})".format(args.scope))

        if args.dry_run:
            action = "retirerait" if args.uninstall else "ajouterait"
            return Resultat("claude-code", "simule", "{} {} via {}".format(action, args.name, binaire))
        if args.uninstall:
            proc = subprocess.run(
                [binaire, "mcp", "remove", args.name, "-s", args.scope],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            if proc.returncode != 0:
                return Resultat("claude-code", "inchange",
                                (proc.stderr or proc.stdout).strip()[:120] or "absent")
            return Resultat("claude-code", "desinstalle", "portée {}".format(args.scope))

        # `add` échoue si le serveur existe déjà : on retire d'abord, sans bruit.
        subprocess.run([binaire, "mcp", "remove", args.name, "-s", args.scope],
                       capture_output=True, text=True)
        commande_cli = [binaire, "mcp", "add", args.name, "-s", args.scope]
        for cle, valeur in conf.get("env", {}).items():
            commande_cli += ["-e", "{}={}".format(cle, valeur)]
        commande_cli += ["--", commande, *arguments]
        proc = subprocess.run(commande_cli, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        if proc.returncode != 0:
            return Resultat("claude-code", "erreur",
                            (proc.stderr or proc.stdout).strip()[:200])
        return Resultat("claude-code", "installe", "portée {} (via {})".format(args.scope, binaire))

    # Repli : édition directe de la configuration utilisateur.
    chemin = Path.home() / ".claude.json"
    if not existe(chemin):
        return Resultat("claude-code", "absent",
                        "ni binaire `claude` ni {}".format(chemin))
    try:
        contenu = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return Resultat("claude-code", "erreur", "{} illisible : {}".format(chemin, exc))

    serveurs = contenu.setdefault("mcpServers", {})
    if args.uninstall:
        if args.name not in serveurs:
            return Resultat("claude-code", "inchange", "{} : absent".format(chemin))
        if args.dry_run:
            return Resultat("claude-code", "simule", "retirerait {} de {}".format(args.name, chemin))
        del serveurs[args.name]
    else:
        if serveurs.get(args.name) == conf:
            return Resultat("claude-code", "inchange", "{} : déjà à jour".format(chemin))
        if args.dry_run:
            return Resultat("claude-code", "simule", "écrirait {} dans {}".format(args.name, chemin))
        serveurs[args.name] = conf

    copie = sauvegarder(chemin)
    chemin.write_text(json.dumps(contenu, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    statut = "desinstalle" if args.uninstall else "installe"
    return Resultat("claude-code", statut,
                    "{} (repli fichier, sauvegarde : {})".format(chemin, copie.name))


# =============================================================================
# Contrôle préalable
# =============================================================================
def verifier_serveur(commande: str, arguments: list[str], env: dict) -> str | None:
    """Vérifie que le module s'importe, pour ne pas déclarer une installation
    qui échouerait au premier lancement du client."""
    environnement = os.environ.copy()
    environnement.update(env)
    proc = subprocess.run(
        [commande, "-c", "import romeo_mcp.server"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=environnement, timeout=120,
    )
    if proc.returncode != 0:
        return (proc.stderr or proc.stdout).strip().splitlines()[-1][:200]
    return None


# =============================================================================
# Entrée
# =============================================================================
def main() -> int:
    parseur = argparse.ArgumentParser(
        description="Installe le serveur MCP ROMEO dans Claude Code, Claude "
                    "Desktop et Codex.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parseur.add_argument("--targets", default="all",
                         help="cibles séparées par des virgules : {} ou `all`".format(
                             ", ".join(CIBLES)))
    parseur.add_argument("--name", default=NOM_DEFAUT, help="nom du serveur MCP")
    parseur.add_argument("--python", dest="python", default=None,
                         help="interpréteur à utiliser (défaut : le venv du projet)")
    parseur.add_argument("--scope", default="user", choices=("local", "user", "project"),
                         help="portée pour Claude Code (défaut : user)")
    parseur.add_argument("--env", action="append", default=[], metavar="CLE=VALEUR",
                         help="variable d'environnement supplémentaire, répétable")
    parseur.add_argument("--no-docs", action="store_true",
                         help="ne pas renseigner ROMEO_DOCS_DIR automatiquement")
    parseur.add_argument("--claude-desktop-config", default=None,
                         help="chemin explicite de claude_desktop_config.json")
    parseur.add_argument("--codex-config", default=None,
                         help="chemin explicite du config.toml de Codex")
    parseur.add_argument("--dry-run", action="store_true",
                         help="montrer ce qui serait fait, sans rien écrire")
    parseur.add_argument("--uninstall", action="store_true", help="retirer le serveur")
    parseur.add_argument("--list", action="store_true", dest="lister",
                         help="afficher les emplacements détectés et sortir")
    parseur.add_argument("--no-check", action="store_true",
                         help="ne pas vérifier que le serveur démarre")
    args = parseur.parse_args()

    racine = racine_projet()
    python = interpreteur(racine, args.python)
    commande = str(python)
    arguments = ["-m", "romeo_mcp"]

    # PYTHONPATH garantit que `-m romeo_mcp` fonctionne même si le paquet n'a
    # pas été installé dans le venv et quel que soit le dossier courant.
    env = {"PYTHONPATH": str(racine)}
    docs = None if args.no_docs else dossier_docs(racine)
    # Le corpus embarque est trouve relativement au paquet. Inscrire son
    # chemin absolu dans le client le casserait apres un deplacement du depot.
    if docs and os.environ.get("ROMEO_DOCS_DIR"):
        env["ROMEO_DOCS_DIR"] = str(docs)
    for paire in args.env:
        if "=" not in paire:
            raise SystemExit("--env attend CLE=VALEUR, reçu : {!r}".format(paire))
        cle, valeur = paire.split("=", 1)
        env[cle] = valeur

    print("Serveur MCP  : {}".format(args.name))
    print("Système      : {}{}".format(sys.platform, " (WSL)" if sous_wsl() else ""))
    print("Projet       : {}".format(racine))
    print("Interpréteur : {}".format(python))
    print("Documentation: {}".format(docs or "non trouvée (search_docs sera inactif)"))
    if sys.platform != "win32" and python.name.lower().endswith(".exe"):
        print()
        print("Note : le seul environnement virtuel trouvé est un venv Windows.")
        print("       Il reste utilisable via l'interopérabilité WSL, mais un venv")
        print("       Linux serait plus robuste côté WSL :")
        print("         python3 -m venv .venv && ./.venv/bin/python -m pip install -e .")
    print()

    if args.lister:
        print("Emplacements recherchés :")
        print("  claude-code    : binaire `claude` ({}), sinon {}".format(
            shutil.which("claude") or "absent", Path.home() / ".claude.json"))
        for etiquette, chemins in (
            ("claude-desktop", candidats_claude_desktop()),
            ("codex", candidats_codex()),
        ):
            print("  {:<15}:".format(etiquette))
            for chemin in chemins:
                print("      [{}] {}".format("x" if existe(chemin) else " ", chemin))
        return 0

    if not args.uninstall and not args.no_check:
        erreur = verifier_serveur(commande, arguments, env)
        if erreur:
            print("Le serveur ne démarre pas. Installation interrompue :")
            print("  {}".format(erreur))
            print()
            print("Vérifie que les dépendances sont installées :")
            print("  {} -m pip install -e {}".format(python, racine))
            return 1

    demandees = CIBLES if args.targets == "all" else tuple(
        t.strip() for t in args.targets.split(",") if t.strip()
    )
    inconnues = [t for t in demandees if t not in CIBLES]
    if inconnues:
        raise SystemExit("cible(s) inconnue(s) : {} (attendu : {})".format(
            ", ".join(inconnues), ", ".join(CIBLES)))

    conf = {"command": commande, "args": arguments}
    if env:
        conf["env"] = env

    resultats = []
    for cible in demandees:
        if cible == "claude-desktop":
            resultats.append(installer_claude_desktop(conf, args))
        elif cible == "codex":
            resultats.append(installer_codex(commande, arguments, env, args))
        elif cible == "claude-code":
            resultats.append(installer_claude_code(conf, commande, arguments, args))

    print("Résultat :")
    for resultat in resultats:
        print("  " + resultat.ligne())

    erreurs = [r for r in resultats if r.statut == "erreur"]
    touchees = [r for r in resultats if r.statut in ("installe", "desinstalle")]

    print()
    if args.dry_run:
        print("Simulation : aucun fichier modifié.")
    elif touchees and not args.uninstall:
        print("Redémarre les applications concernées pour qu'elles relisent leur "
              "configuration.")
    elif not touchees and not erreurs:
        print("Rien à faire.")

    return 1 if erreurs else 0


if __name__ == "__main__":
    raise SystemExit(main())
