"""Catalogue Spack et verification MPI sur un noeud alloue (stdlib seule)."""
from __future__ import annotations

import json
import os
import platform
import re
import shlex
import shutil
import struct
import subprocess
from pathlib import Path

try:
    from .checkpoint_protocol import hash_file
except ImportError:  # Copie autonome dans le job.
    from checkpoint_protocol import hash_file


def parse_spack_catalog(output):
    """Accepte les JSON Spack 0.x/1.x ; une sortie ancienne reste moins precise."""
    start = output.find("[")
    if start >= 0:
        try:
            values, _ = json.JSONDecoder().raw_decode(output[start:])
        except ValueError as exc:
            raise ValueError("Catalogue JSON Spack incomplet") from exc
        if not isinstance(values, list) or len(values) > 20000 or any(not isinstance(v, dict) for v in values):
            raise ValueError("Catalogue JSON Spack invalide ou trop volumineux")
        indexed = {item.get("hash"): item for item in values}
        result = []
        for item in values:
            name, version, sha = item.get("name"), item.get("version"), item.get("hash")
            if not isinstance(name, str) or not isinstance(version, str) or not isinstance(sha, str) or not re.fullmatch(r"[a-z0-9]{7,64}", sha):
                raise ValueError("Specification Spack sans nom, version ou empreinte")
            compiler = item.get("compiler")
            dependencies = item.get("dependencies", [])
            compilers = []
            if isinstance(compiler, dict) and compiler.get("name"):
                compilers.append(compiler)
            legacy_compiler = (item.get("annotations") or {}).get("compiler")
            if not compilers and isinstance(legacy_compiler, str) and "@" in legacy_compiler:
                compiler_name, compiler_version = legacy_compiler.split("@", 1)
                compilers.append({"name": compiler_name, "version": compiler_version, "source": "spack_annotation"})
            for dependency in dependencies if isinstance(dependencies, list) else []:
                virtuals = dependency.get("parameters", {}).get("virtuals", [])
                if dependency.get("name") in {"gcc", "llvm", "aocc", "nvhpc", "intel-oneapi-compilers"} or set(virtuals) & {"c", "cxx", "fortran"}:
                    node = indexed.get(dependency.get("hash"), dependency)
                    compilers.append({"name": node.get("name"), "version": node.get("version"), "hash": node.get("hash")})
            result.append({"package": name + "@" + version, "name": name, "version": version,
                           "hash": sha, "load_spec": "/" + sha, "compilers": compilers,
                           "variants": item.get("parameters", {}), "architecture": item.get("arch"),
                           "dependencies": dependencies, "details_available": True})
        return sorted(result, key=lambda p: (p["package"], p["hash"]))
    # Compatibilite des anciennes observations ; aucun detail n'est invente.
    return [{"package": p, "name": p.split("@")[0], "version": p.split("@", 1)[1],
             "hash": None, "load_spec": p, "compilers": [], "variants": {},
             "architecture": None, "dependencies": [], "details_available": False}
            for p in sorted({line.strip() for line in output.splitlines() if "@" in line and not line.startswith("-")})]


def validate_mpi_request(request, arch, distributed):
    if not isinstance(request, dict) or set(request) - {"provider", "executable", "spack_hash", "compiler", "library_sha256"}:
        raise ValueError("mpi_environment attend provider, executable et les empreintes/options documentees")
    if distributed != "mpi":
        raise ValueError("mpi_environment exige distributed='mpi'")
    provider = request.get("provider", "hpcx" if arch == "armgpu" else "openmpi")
    if provider != ("hpcx" if arch == "armgpu" else "openmpi"):
        raise ValueError("ROMEO : OpenMPI sur x64cpu, NVHPC/HPC-X sur armgpu")
    executable = request.get("executable", "")
    if not isinstance(executable, str) or not executable.startswith("/") or any(c in executable for c in "\n\x00"):
        raise ValueError("mpi_environment.executable doit etre le chemin absolu du binaire MPI")
    for key, pattern in (("spack_hash", r"[a-z0-9]{7,64}"), ("library_sha256", r"[a-f0-9]{64}"),
                         ("compiler", r"[A-Za-z0-9_.+-]+(?:@[A-Za-z0-9_.+-]+)?")):
        if request.get(key) is not None and (not isinstance(request[key], str) or not re.fullmatch(pattern, request[key])):
            raise ValueError("mpi_environment.%s invalide" % key)
    return {**request, "provider": provider}


def elf_machine(path):
    with Path(path).open("rb") as stream:
        header = stream.read(20)
    if len(header) != 20 or header[:4] != b"\x7fELF" or header[5] not in {1, 2}:
        raise ValueError("Executable MPI non ELF ; declarer un binaire compile pour le noeud")
    code = struct.unpack("<H" if header[5] == 1 else ">H", header[18:20])[0]
    return {62: "x86_64", 183: "aarch64"}.get(code, "elf-machine-%d" % code)


def command_output(argv):
    result = subprocess.run(argv, check=False, capture_output=True, text=True, timeout=20)
    if result.returncode or len(result.stdout) + len(result.stderr) > 65536:
        raise ValueError("Verification MPI en echec : " + argv[0])
    return result.stdout.strip()


def verify_mpi(request, arch):
    expected = "aarch64" if arch == "armgpu" else "x86_64"
    if platform.machine().lower() != expected or elf_machine(request["executable"]) != expected:
        raise ValueError("Architecture du noeud ou de l'executable MPI incompatible")
    loaded = sorted(filter(None, os.environ.get("SPACK_LOADED_HASHES", "").split(":")))
    if request.get("spack_hash") and not any(h.startswith(request["spack_hash"]) for h in loaded):
        raise ValueError("Empreinte Spack demandee non chargee dans l'allocation")
    compiler_path = shutil.which("mpicc")
    if not compiler_path:
        raise ValueError("mpicc absent de l'environnement selectionne")
    compiler = command_output([compiler_path, "--showme:command"])
    version = command_output([compiler_path, "--showme:version"])
    link = command_output([compiler_path, "--showme:link"])
    directories = [Path(token[2:]).resolve() for token in shlex.split(link) if token.startswith("-L")]
    dependencies = command_output(["ldd", request["executable"]])
    if "not found" in dependencies:
        raise ValueError("Bibliotheque partagee de l'executable MPI introuvable")
    libraries = []
    for line in dependencies.splitlines():
        match = re.match(r"\s*(libmpi(?:\.so[^\s]*))\s*=>\s*(/[^\s]+)", line)
        if match:
            libraries.append(Path(match[2]).resolve())
    if not libraries:
        raise ValueError("Aucune libmpi dynamique observable : compatibilite d'un binaire statique non prouvable")
    if any(lib.parent not in directories or elf_machine(lib) != expected for lib in libraries):
        raise ValueError("L'executable ne lie pas la libmpi de l'environnement mpicc selectionne")
    provider_evidence = str(Path(compiler_path).resolve()) + " " + link + " " + os.environ.get("HPCX_MPI_DIR", "")
    if request["provider"] == "hpcx" and "hpcx" not in provider_evidence.lower().replace("-", ""):
        raise ValueError("Le fournisseur NVHPC/HPC-X demande n'a pas ete observe")
    if request["provider"] == "openmpi" and "open mpi" not in version.lower() and "openmpi" not in version.lower():
        raise ValueError("Le fournisseur OpenMPI demande n'a pas ete observe")
    compiler_version = None
    if request.get("compiler"):
        name, _, number = request["compiler"].partition("@")
        tokens = shlex.split(compiler)
        if not tokens:
            raise ValueError("Wrapper MPI sans compilateur observable")
        selected_compiler = shutil.which(tokens[0]) or tokens[0]
        basename = Path(tokens[0]).name
        version_flag = "-V" if basename in {"nvc", "nvc++", "nvfortran"} else "--version"
        compiler_version = command_output([tokens[0], version_flag])
        aliases = {"aocc": {"clang", "clang++", "flang"}, "llvm": {"clang", "clang++", "flang"},
                   "nvhpc": {"nvc", "nvc++", "nvfortran"}}
        matches = name in basename or basename in aliases.get(name, set())
        vendor_evidence = str(selected_compiler) + " " + compiler_version
        if name == "aocc":
            matches = matches and ("aocc" in vendor_evidence.lower() or "amd clang" in vendor_evidence.lower())
        if not matches:
            raise ValueError("Compilateur du wrapper MPI different du compilateur demande")
        if number and number not in vendor_evidence:
            raise ValueError("Version du compilateur MPI differente de la version demandee")
    evidence = [{"path": str(lib), **hash_file(lib)} for lib in libraries]
    if request.get("library_sha256") and any(lib["sha256"] != request["library_sha256"] for lib in evidence):
        raise ValueError("Empreinte de libmpi differente de l'empreinte demandee")
    return {"provider": request["provider"], "architecture": expected, "mpicc": str(Path(compiler_path).resolve()),
            "compiler_command": compiler, "compiler_version": compiler_version,
            "version": version, "libraries": evidence, "spack_hashes": loaded,
            "linkage_verified": True, "mpi_collectives_validated": False}
