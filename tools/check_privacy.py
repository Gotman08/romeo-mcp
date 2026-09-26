#!/usr/bin/env python3
"""Controle sans dependance des fichiers indexes et, en option, de l'historique.

Les rapports ne contiennent jamais les valeurs trouvees. Ce controle cible
des motifs connus et ne remplace pas une relecture humaine.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
EMAIL = re.compile(r"[A-Za-z0-9_.+%-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
PUBLIC_DOMAINS = {"users.noreply.github.com", "noreply.github.com", "example.com", "example.org", "example.net"}
TOKENS = {
    "cle privee": re.compile(r"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----"),
    "jeton GitHub": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{70,})\b"),
    "jeton de service": re.compile(r"\b(?:hf_[A-Za-z0-9]{30,}|sk-proj-[A-Za-z0-9_-]{40,}|AKIA[A-Z0-9]{16})\b"),
    "URL avec mot de passe": re.compile(r"https?://[^\s/:]+:[^\s/@]+@"),
}
PROFILE = re.compile(r"(?:[A-Z]:[\\/](?:Users|Documents and Settings)[\\/]|/(?:home|Users)/)([\w.-]+)", re.I)
EXAMPLE_USERS = {"user", "utilisateur", "username", "your-user", "votre_identifiant", "moi", "alice", "bob", "test"}


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(ROOT), *args], stderr=subprocess.PIPE)


def path_issues(path: str) -> list[str]:
    p = PurePosixPath(path.lower())
    name = p.name
    if (name in {".env", ".mcp.json", "config.local.json", "credentials.json", "jobs.db"}
            or (name.startswith(".env.") and name not in {".env.example", ".env.template"})
            or name in {"id_rsa", "id_ed25519", "id_ecdsa"}
            or p.suffix in {".pem", ".p12", ".pfx", ".key", ".db", ".sqlite", ".sqlite3", ".log"}
            or any(x in p.parts for x in (".ssh", ".codex", ".claude", ".venv", "venv", ".romeo-mcp"))):
        return ["fichier prive ou genere"]
    return []


def inspect_text(path: str, raw: bytes, metadata: bool = False) -> list[tuple[int, str]]:
    if b"\x00" in raw:
        return []
    text = raw.decode("utf-8", errors="replace")
    findings = []
    official = path.startswith("romeo_mcp/documentation/")
    for number, line in enumerate(text.splitlines(), 1):
        for label, pattern in TOKENS.items():
            if pattern.search(line):
                findings.append((number, label))
        for match in EMAIL.finditer(line):
            domain = match[1].lower()
            # Contacts publies dans le corpus officiel, pas identites de commit.
            # Identifiant technique public des remotes SSH, pas une adresse personnelle.
            ssh_remote = (not metadata and match[0].split("@")[0] == "git" and domain == "github.com"
                          and line[match.end():].startswith(":"))
            allowed = domain in PUBLIC_DOMAINS or (official and domain.endswith("univ-reims.fr")) or ssh_remote
            if not allowed:
                findings.append((number, "adresse de commit non noreply" if metadata else "adresse a verifier"))
        if not official:
            for match in PROFILE.finditer(line):
                if match[1].lower() not in EXAMPLE_USERS:
                    findings.append((number, "chemin de profil personnel"))
            if re.search(r"\br[0-9]{6}\b", line) and "r000000" not in line.lower():
                findings.append((number, "code de projet reel possible"))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--history", action="store_true", help="examiner tous les objets accessibles par les refs Git")
    parser.add_argument("--staged", action="store_true", help="verifier aussi l'identite du prochain commit")
    args = parser.parse_args()
    findings = set()
    scanned = set()

    def inspect(path, raw, oid="index", metadata=False):
        for label in ([] if metadata else path_issues(path)):
            findings.add((path, 0, label, oid[:12]))
        if (oid, path) in scanned:
            return
        scanned.add((oid, path))
        for line, label in inspect_text(path, raw, metadata):
            findings.add((path, line, label, oid[:12]))

    # Toujours lire l'index, pas une copie de travail qui pourrait masquer ce
    # qui sera reellement commis. Les noms sont delimites par NUL.
    for entry in git("ls-files", "--stage", "-z").split(b"\0"):
        if not entry:
            continue
        info, filename = entry.split(b"\t", 1)
        _, oid, stage = info.split()
        path = filename.decode("utf-8", errors="replace")
        if stage != b"0":
            findings.add((path, 0, "conflit non resolu", "index"))
            continue
        inspect(path, git("cat-file", "blob", oid.decode()), oid.decode())

    if args.staged:
        for role in ("GIT_AUTHOR_IDENT", "GIT_COMMITTER_IDENT"):
            inspect(role, git("var", role), metadata=True)

    if args.history:
        for entry in git("rev-list", "--objects", "--all").decode("utf-8", errors="replace").splitlines():
            oid, _, path = entry.partition(" ")
            kind = git("cat-file", "-t", oid).strip()
            if kind in (b"blob", b"commit", b"tag"):
                inspect(path or kind.decode(), git("cat-file", "-p", oid), oid, kind != b"blob")
        # Un meme blob peut avoir ete porte par plusieurs noms, dont un prive.
        for oid in git("rev-list", "--all").decode().splitlines():
            for path in git("ls-tree", "-r", "--name-only", "-z", oid).decode().split("\0"):
                for label in path_issues(path) if path else []:
                    findings.add((path, 0, label, oid[:12]))

    for path, line, label, oid in sorted(findings):
        print(f"{path}:{line}: {label} [{oid}]")
    print(f"Confidentialite : {len(scanned)} contenus examines, {len(findings)} signalement(s).")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
