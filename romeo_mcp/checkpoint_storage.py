"""Copies de checkpoints et retention prudente, executees dans l'allocation."""
from __future__ import annotations

import math
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

try:
    from .checkpoint_protocol import (GENERATION, MAX_GENERATIONS, _sync_directory, atomic_json, hash_file,
                                      no_symlinks, safe_file, sync_directories, verify_checkpoint)
except ImportError:
    from checkpoint_protocol import (GENERATION, MAX_GENERATIONS, _sync_directory, atomic_json, hash_file,
                                     no_symlinks, safe_file, sync_directories, verify_checkpoint)


def quota_capacity(output, filesystem, fileset, required_bytes, required_files):
    """mmlsquota --block-size 1K : blocs ET inodes, y compris in_doubt."""
    rows = [line.split() for line in output.splitlines()]
    rows = [parts for parts in rows if len(parts) >= 13 and parts[:2] == [filesystem, fileset]]
    if len(rows) != 1:
        raise ValueError("Quota du fileset introuvable ou ambigu ; aucune suppression/copie autorisee")
    row = rows[0]
    try:
        blocks, soft, hard, doubt = (int(v) for v in row[3:7])
        files, files_soft, files_hard, files_doubt = (int(v) for v in row[8:12])
    except ValueError as exc:
        raise ValueError("Quota non numerique ; demander --block-size 1K") from exc
    if any(v < 0 for v in (blocks, soft, hard, doubt, files, files_soft, files_hard, files_doubt)):
        raise ValueError("Quota invalide")
    if row[7].lower() == "expired" or row[12].lower() == "expired":
        raise ValueError("Quota de blocs ou d'inodes : delai de grace expire")
    byte_limit = min((v for v in (soft, hard) if v > 0), default=0)
    file_limit = min((v for v in (files_soft, files_hard) if v > 0), default=0)
    if byte_limit and blocks + doubt + math.ceil(required_bytes / 1024) > byte_limit:
        raise ValueError("Quota de blocs insuffisant pour conserver une copie complete")
    if file_limit and files + files_doubt + required_files > file_limit:
        raise ValueError("Quota d'inodes insuffisant pour conserver une copie complete")
    return {"filesystem": filesystem, "fileset": fileset, "checked_at": time.time(),
            "blocks_kib": blocks, "files": files, "in_doubt_kib": doubt, "in_doubt_files": files_doubt,
            "required_bytes": required_bytes, "required_files": required_files}


def check_quota(policy, required_bytes, required_files):
    command = ["mmlsquota", "--block-size", "1K"]
    command += ["-g", policy["group"]] if policy.get("group") else ["-u", os.environ.get("USER", "")]
    command.append(policy["filesystem"])
    result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=30)
    if result.returncode or len(result.stdout) > 65536:
        raise ValueError("Quota non observe ; les checkpoints originaux sont conserves")
    return quota_capacity(result.stdout, policy["filesystem"], policy["fileset"], required_bytes, required_files)


def _copy_file(source, target, entry, deadline):
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with Path(source).open("rb") as stream, target.open("xb") as destination:
        os.chmod(target, 0o600)
        total = 0
        while block := stream.read(1024 * 1024):
            total += len(block)
            if total > entry["size"] or time.monotonic() > deadline:
                raise ValueError("Source modifiee ou budget de copie depasse")
            destination.write(block)
        destination.flush()
        os.fsync(destination.fileno())
    if hash_file(target, max_bytes=entry["size"], deadline=deadline) != entry:
        raise ValueError("Copie de checkpoint corrompue")
    parent = target.parent
    _sync_directory(parent)


def copy_verified(checkpoint, backup_dir, quota, *, timeout=900, quota_checker=check_quota):
    if checkpoint.get("integrity_verified") is not True:
        raise ValueError("Seul un checkpoint verifie peut etre protege")
    manifest = checkpoint["manifest"]
    destination = no_symlinks(Path(backup_dir) / manifest["run_id"] / Path(checkpoint["directory"]).name)
    source = no_symlinks(checkpoint["directory"])
    if source == destination or source.is_relative_to(destination) or destination.is_relative_to(source):
        raise ValueError("La copie doit etre hors du repertoire du checkpoint original")
    if destination.exists():
        verified = verify_checkpoint(destination / "manifest.json", binding=manifest["binding"],
                                     run_id=manifest["run_id"], world_size=manifest["world_size"])
        if verified["manifest_sha256"] != checkpoint["manifest_sha256"]:
            raise ValueError("Une generation differente existe deja a la destination")
        return {"directory": str(destination), "manifest_sha256": verified["manifest_sha256"],
                "copy_validated": True, "independent_backup": False, "already_present": True}
    # Les limites concernent aussi les repertoires intermediaires et les metadonnees.
    directories = {parent for entry in manifest["files"] for parent in Path(entry["path"]).parents
                   if parent != Path(".")}
    new_parents = sum(not parent.exists() for parent in (destination.parent, *destination.parent.parents))
    capacity = quota_checker(quota, checkpoint["bytes"] + 2 * 1024 * 1024,
                             len(manifest["files"]) + len(directories) + new_parents + 4)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = destination.with_name(".copy-" + uuid.uuid4().hex)
    temporary.mkdir(mode=0o700)
    deadline = time.monotonic() + timeout
    try:
        for entry in manifest["files"]:
            _copy_file(safe_file(source, entry["path"]), safe_file(temporary, entry["path"]),
                       {"size": entry["size"], "sha256": entry["sha256"]}, deadline)
        original_manifest = source / "manifest.json"
        _copy_file(original_manifest, temporary / "manifest.json", hash_file(original_manifest), deadline)
        if hash_file(temporary / "manifest.json")["sha256"] != checkpoint["manifest_sha256"]:
            raise ValueError("Manifeste source remplace pendant la copie")
        sync_directories(temporary, [entry["path"] for entry in manifest["files"]])
        # La generation apparait uniquement apres verification de tous les fichiers.
        os.rename(temporary, destination)
        _sync_directory(destination.parent)
        verified = verify_checkpoint(destination / "manifest.json", binding=manifest["binding"],
                                     run_id=manifest["run_id"], world_size=manifest["world_size"], deadline=deadline)
        return {"directory": str(destination), "manifest_sha256": verified["manifest_sha256"],
                "copy_validated": True, "independent_backup": False, "quota": capacity}
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def retain_protected(root, backup_dir, checkpoint, keep_last, *, timeout=900):
    """Ne supprime une generation source que si sa copie est encore verifiee."""
    manifest = checkpoint["manifest"]
    run = no_symlinks(Path(root) / manifest["run_id"])
    candidates = sorted((p for p in run.iterdir() if GENERATION.fullmatch(p.name)),
                        key=lambda p: p.name, reverse=True)
    if len(candidates) > MAX_GENERATIONS:
        raise ValueError("Trop de generations pour une retention bornee")
    removed, preserved, kept = [], [], []
    deadline = time.monotonic() + timeout
    for folder in candidates:
        try:
            original = verify_checkpoint(folder / "manifest.json", binding=manifest["binding"], deadline=deadline)
            if len(kept) < keep_last or folder == Path(checkpoint["directory"]):
                kept.append(folder.name)
                continue
            copy = verify_checkpoint(Path(backup_dir) / manifest["run_id"] / folder.name / "manifest.json",
                                     binding=manifest["binding"], deadline=deadline)
            if original["manifest_sha256"] != copy["manifest_sha256"]:
                raise ValueError("Copie non associee a l'original")
            # Les racines et liens sont controles avant la suppression native.
            if no_symlinks(folder).parent != run:
                raise ValueError("Generation active ou chemin hors du calcul")
            shutil.rmtree(folder)
            removed.append(folder.name)
        except (OSError, ValueError) as exc:
            preserved.append({"generation": folder.name, "reason": str(exc)[:200]})
    return {"keep_last": keep_last, "kept_valid_generations": kept, "removed": removed, "preserved": preserved,
            "backup_retention": "Les copies protegees sont conservees ; aucune suppression automatique de la derniere copie."}


def protect(checkpoint, root, backup_dir, quota, keep_last=3, timeout=900):
    run = no_symlinks(Path(backup_dir) / checkpoint["manifest"]["run_id"])
    run.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = run / ".protection.lock"
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    try:
        result = copy_verified(checkpoint, backup_dir, quota, timeout=timeout)
        result["retention"] = retain_protected(root, backup_dir, checkpoint, keep_last, timeout=timeout)
        atomic_json(run / "protection.json", result)
        return result
    finally:
        lock.unlink()
