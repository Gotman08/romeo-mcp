#!/usr/bin/env python3
"""Valide une release et prepare ses empreintes et notes avant publication."""

import argparse
from email.parser import Parser
import hashlib
from pathlib import Path
import re
import tarfile
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
#: Verrous exiges dans la wheel, avec le paquet qu'ils doivent figer.
REQUIRED_LOCKS = {"romeo_mcp/locks/server.lock": "mcp", "romeo_mcp/locks/verifier.lock": "sigstore"}


def lock_problem(text: str, package: str) -> str | None:
    """Chaque exigence doit etre figee a une version et porter au moins une empreinte."""
    requirements = [line for line in re.sub(r"\\\n\s*", " ", text).splitlines()
                    if line.strip() and not line.lstrip().startswith("#")]
    if not any(line.startswith(package + "==") for line in requirements):
        return f"{package} absent du verrou"
    for line in requirements:
        if not re.match(r"[A-Za-z0-9._-]+==[^ ;]+", line) or "--hash=sha256:" not in line:
            return "exigence sans version figee ou sans empreinte"
    return None


def prepare(tag: str, root: Path = ROOT) -> list[Path]:
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag):
        raise ValueError("Tag stable attendu : vX.Y.Z.")
    version = tag[1:]
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    source = (root / "romeo_mcp/__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*[\'"]([^\'"]+)[\'"]', source, re.M)
    if metadata["project"]["version"] != version or not match or match[1] != version:
        raise ValueError("Le tag et les deux versions du paquet doivent correspondre.")
    dist = root / "dist"
    wheel = dist / f"romeo_mcp-{version}-py3-none-any.whl"
    sdist = dist / f"romeo_mcp-{version}.tar.gz"
    with zipfile.ZipFile(wheel) as archive:
        packaged = Parser().parsestr(archive.read(f"romeo_mcp-{version}.dist-info/METADATA").decode())
        if packaged["Version"] != version or packaged["Name"] != "romeo-mcp":
            raise ValueError("Metadonnees de wheel incoherentes.")
        for name, package in REQUIRED_LOCKS.items():
            problem = lock_problem(archive.read(name).decode(), package)
            if problem:
                raise ValueError(f"{name} : {problem}.")
    with tarfile.open(sdist) as archive:
        stream = archive.extractfile(f"romeo_mcp-{version}/pyproject.toml")
        if stream is None or tomllib.loads(stream.read().decode())["project"]["version"] != version:
            raise ValueError("Version du paquet source incoherente.")
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    notes = re.search(r"^## " + re.escape(version) + r"\s*\n(.*?)(?=^## |\Z)", changelog, re.M | re.S)
    if not notes or not notes[1].strip():
        raise ValueError("Section de version manquante dans CHANGELOG.md.")
    sums = dist / "SHA256SUMS"
    sums.write_text("".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in (wheel, sdist)), encoding="utf-8")
    (dist / "release-notes.md").write_text(notes[1].strip() + "\n", encoding="utf-8")
    return [wheel, sdist, sums]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    try:
        for path in prepare(args.tag):
            print(path.name)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, tarfile.TarError) as exc:
        parser.exit(1, f"Release refusee : {exc}\n")


if __name__ == "__main__":
    main()
