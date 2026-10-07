"""Protocole de checkpoint portable, utilisable sans MCP, SSH ni bibliotheque MPI.

Les applications publient le manifeste en dernier, apres fermeture des fichiers
et synchronisation des rangs. Les preuves concernent les entrees declarees et
les declarations applicatives ; elles ne certifient pas la justesse du calcul.
Ce module est aussi depose tel quel dans les allocations Slurm.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import uuid
from pathlib import Path, PurePosixPath

SCHEMA = "romeo-checkpoint-v1"
MAX_JSON = 1024 * 1024
MAX_FILES = 16384
MAX_GENERATIONS = 1000
MAX_RANKS = 16384
HEX = re.compile(r"[a-f0-9]{64}")
IDENTITY = re.compile(r"[A-Za-z0-9_.-]{1,64}")
GENERATION = re.compile(r"generation-([0-9]{20})")


def integer(value, minimum=0, maximum=2**63 - 1):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("Entier hors limites dans le contrat de checkpoint")
    return value


def identity(value):
    if not isinstance(value, str) or not IDENTITY.fullmatch(value) or value in {".", ".."}:
        raise ValueError("Identifiant de calcul invalide")
    return value


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def no_symlinks(path):
    path = Path(path).absolute()
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("Un checkpoint ne peut pas traverser un lien symbolique")
    return path


def safe_file(base, relative):
    if not isinstance(relative, str) or "\\" in relative or "\x00" in relative:
        raise ValueError("Chemin de checkpoint invalide")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or any(p in {"", ".", ".."} for p in relative.split("/")):
        raise ValueError("Chemin de checkpoint hors de sa generation")
    base = no_symlinks(base)
    candidate = no_symlinks(base.joinpath(*pure.parts))
    if not candidate.is_relative_to(base):
        raise ValueError("Chemin de checkpoint hors de sa generation")
    return candidate


def _unique_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Cle JSON dupliquee")
        value[key] = item
    return value


def read_json(path, limit=MAX_JSON):
    path = no_symlinks(path)
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Document de checkpoint trop volumineux")
    value = json.loads(data, object_pairs_hook=_unique_pairs,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nombre JSON non fini")))
    if not isinstance(value, dict):
        raise ValueError("Un objet JSON est attendu")
    return value


def _sync_directory(directory):
    if os.name != "nt":
        fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def sync_directories(directory, relative_files):
    directory = no_symlinks(directory)
    folders = {directory}
    for relative in relative_files:
        parent = safe_file(directory, relative).parent
        while parent.is_relative_to(directory):
            folders.add(parent)
            if parent == directory:
                break
            parent = parent.parent
    for folder in sorted(folders, key=lambda p: len(p.parts), reverse=True):
        _sync_directory(folder)


def atomic_json(path, value, *, immutable=False):
    path = no_symlinks(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    data = canonical(value)
    if len(data) > MAX_JSON:
        raise ValueError("Document de checkpoint trop volumineux")
    temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("xb") as stream:
            os.chmod(temporary, 0o600)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if immutable:
            # Publication atomique sans ecraser une generation deja publiee.
            os.link(temporary, path)
            temporary.unlink()
        else:
            os.replace(temporary, path)
        _sync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def hash_file(path, *, max_bytes=2**40, deadline=None, sync=False):
    path = no_symlinks(path)
    before = path.stat()
    if not path.is_file() or before.st_size > max_bytes:
        raise ValueError("Fichier absent, non regulier ou trop volumineux")
    sha = hashlib.sha256()
    with path.open("r+b" if sync and os.name == "nt" else "rb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError("Fichier remplace pendant son ouverture")
        total = 0
        while block := stream.read(1024 * 1024):
            total += len(block)
            if total > max_bytes or (deadline is not None and time.monotonic() > deadline):
                raise ValueError("Budget de verification des fichiers depasse")
            sha.update(block)
        if sync:
            os.fsync(stream.fileno())
        after = os.fstat(stream.fileno())
    final = path.stat()
    stamp = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    # Windows peut exposer un ChangeTime different entre stat et fstat.
    # Comparer chaque source avant/apres, puis les champs communs, conserve
    # la detection de remplacement et mutation sans faux positif de portabilite.
    common = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
    if stamp(before) != stamp(final) or stamp(opened) != stamp(after) or common(after) != common(final):
        raise ValueError("Fichier modifie pendant la verification")
    return {"sha256": sha.hexdigest(), "size": total}


def workload_binding(command, code_files, data_files, environment, *, max_bytes=2**40, timeout=900):
    if not code_files or len(code_files) + len(data_files) > 128:
        raise ValueError("Declare entre 1 et 128 fichiers de programme et de donnees")
    deadline = time.monotonic() + timeout
    remaining = max_bytes
    def collect(paths):
        nonlocal remaining
        result = []
        for name in sorted(set(paths)):
            observed = hash_file(name, max_bytes=remaining, deadline=deadline)
            remaining -= observed["size"]
            result.append({"path": str(Path(name).absolute()), **observed})
        return result
    return {"command_sha256": hashlib.sha256(command.encode()).hexdigest(),
            "code": collect(code_files), "data": collect(data_files), "environment": environment}


def generation_directory(root, run_id, generation):
    return no_symlinks(Path(root) / identity(run_id) / ("generation-%020d" % integer(generation)))


def validate_manifest(value, directory, *, run_id=None, binding=None, world_size=None):
    if value.get("schema") != SCHEMA or value.get("complete") is not True:
        raise ValueError("Checkpoint incomplet ou schema inconnu")
    actual_run = identity(value.get("run_id"))
    generation = integer(value.get("generation"))
    step = integer(value.get("step"))
    world = integer(value.get("world_size"), 1, MAX_RANKS)
    if run_id is not None and actual_run != run_id:
        raise ValueError("Checkpoint associe a un autre calcul")
    if world_size is not None and world != world_size:
        raise ValueError("Nombre de rangs incompatible avec la reprise")
    if Path(directory).name != "generation-%020d" % generation:
        raise ValueError("Generation du manifeste incoherente avec son repertoire")
    steps = value.get("rank_steps")
    if not isinstance(steps, list) or len(steps) != world or any(type(s) is not int or s != step for s in steps):
        raise ValueError("Les rangs n'ont pas publie la meme etape coherente")
    declared_binding = value.get("binding")
    if not isinstance(declared_binding, dict) or value.get("binding_sha256") != digest(declared_binding):
        raise ValueError("Association au programme et aux donnees absente ou alteree")
    if binding is not None and digest(binding) != value["binding_sha256"]:
        raise ValueError("Programme, donnees ou environnement differents du checkpoint")
    published = value.get("published_at")
    if type(published) not in {int, float} or not math.isfinite(published):
        raise ValueError("Date de publication invalide")
    files = value.get("files")
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES:
        raise ValueError("Liste de fichiers de checkpoint absente ou hors limites")
    seen, covered = set(), set()
    for entry in files:
        if not isinstance(entry, dict):
            raise ValueError("Entree de fichier invalide")
        target = safe_file(directory, entry.get("path"))
        if target in seen or target.name == "manifest.json":
            raise ValueError("Fichier de checkpoint duplique ou reserve")
        seen.add(target)
        integer(entry.get("size"))
        if not isinstance(entry.get("sha256"), str) or not HEX.fullmatch(entry["sha256"]):
            raise ValueError("Empreinte SHA-256 absente ou invalide")
        ranks = entry.get("ranks")
        if not isinstance(ranks, list) or not ranks or any(type(r) is not int for r in ranks) or len(ranks) != len(set(ranks)):
            raise ValueError("Couverture des rangs absente ou dupliquee")
        covered.update(integer(rank, 0, world - 1) for rank in ranks)
    if covered != set(range(world)):
        raise ValueError("Les fichiers ne couvrent pas tous les rangs du calcul")
    return value


def verify_checkpoint(manifest_path, *, run_id=None, binding=None, world_size=None,
                      verify_files=True, max_bytes=2**40, deadline=None, expected_binding_sha256=None):
    path = no_symlinks(manifest_path)
    before = hash_file(path, max_bytes=MAX_JSON, deadline=deadline)
    value = validate_manifest(read_json(path), path.parent, run_id=run_id, binding=binding, world_size=world_size)
    if expected_binding_sha256 is not None and value["binding_sha256"] != expected_binding_sha256:
        raise ValueError("Checkpoint sans association au job source choisi")
    required = sum(entry["size"] for entry in value["files"])
    if required > max_bytes:
        raise ValueError("Checkpoint au-dessus du budget de verification")
    if verify_files:
        for entry in value["files"]:
            observed = hash_file(safe_file(path.parent, entry["path"]), max_bytes=entry["size"], deadline=deadline)
            if observed != {"sha256": entry["sha256"], "size": entry["size"]}:
                raise ValueError("Checkpoint corrompu : " + entry["path"])
    if before != hash_file(path, max_bytes=MAX_JSON, deadline=deadline):
        raise ValueError("Manifeste modifie pendant la verification")
    return {"manifest": value, "manifest_path": str(path), "manifest_sha256": before["sha256"],
            "directory": str(path.parent), "bytes": required, "integrity_verified": verify_files}


def discover(root, run_id, *, binding=None, world_size=None, verify_files=True,
             max_bytes=2**40, timeout=900, expected_binding_sha256=None):
    directory = no_symlinks(Path(root) / identity(run_id))
    candidates = []
    if directory.exists():
        for item in directory.iterdir():
            match = GENERATION.fullmatch(item.name)
            if match:
                candidates.append((int(match[1]), item))
                if len(candidates) > MAX_GENERATIONS:
                    raise ValueError("Trop de generations : appliquer la retention des checkpoints")
    rejected = []
    deadline = time.monotonic() + timeout
    for generation, folder in sorted(candidates, reverse=True):
        try:
            checkpoint = verify_checkpoint(folder / "manifest.json", run_id=run_id, binding=binding,
                                           world_size=world_size, verify_files=verify_files,
                                           max_bytes=max_bytes, deadline=deadline, expected_binding_sha256=expected_binding_sha256)
            return {"checkpoint": checkpoint, "rejected": rejected, "generations_seen": len(candidates)}
        except (OSError, ValueError) as exc:
            rejected.append({"generation": generation, "reason": str(exc)[:300]})
    return {"checkpoint": None, "rejected": rejected, "generations_seen": len(candidates)}


def publish(root, run_id, generation, step, world_size, files, rank_steps, binding,
            *, signal_request_id=None, max_bytes=2**40, timeout=900):
    """Publie apres la barriere applicative ; chaque fichier a sa couverture de rangs."""
    directory = generation_directory(root, run_id, generation)
    entries, remaining = [], max_bytes
    deadline = time.monotonic() + timeout
    for entry in files:
        observed = hash_file(safe_file(directory, entry["path"]), max_bytes=remaining, deadline=deadline, sync=True)
        remaining -= observed["size"]
        entries.append({"path": entry["path"], "ranks": entry["ranks"], **observed})
    value = {"schema": SCHEMA, "complete": True, "run_id": run_id, "generation": generation,
             "step": step, "world_size": world_size, "rank_steps": rank_steps,
             "binding": binding, "binding_sha256": digest(binding), "files": entries,
             "published_at": time.time(), "signal_request_id": signal_request_id}
    validate_manifest(value, directory)
    sync_directories(directory, [entry["path"] for entry in files])
    atomic_json(directory / "manifest.json", value, immutable=True)
    _sync_directory(directory.parent)
    return str(directory / "manifest.json")


def application_context():
    return read_json(Path(os.environ["ROMEO_CHECKPOINT_ATTEMPT"]) / "context.json")


def record_event(kind, step, *, rank=None):
    """L'application appelle loaded APRES chargement, progress APRES calcul utile."""
    if kind not in {"loaded", "progress", "completed", "signal_ack"}:
        raise ValueError("Preuve applicative inconnue")
    context = application_context()
    rank = integer(int(os.environ.get("RANK", os.environ.get("SLURM_PROCID", "0"))) if rank is None else rank, 0, context["world_size"] - 1)
    value = {"kind": kind, "attempt_id": context["attempt_id"], "run_id": context["run_id"],
             "job_id": context["job_id"], "binding_sha256": context["binding_sha256"], "rank": rank,
             "step": integer(step), "checkpoint_sha256": context.get("checkpoint_sha256"), "observed_at": time.time()}
    attempt = Path(os.environ["ROMEO_CHECKPOINT_ATTEMPT"])
    if kind == "signal_ack":
        value["request_id"] = read_json(attempt / "signal.json")["request_id"]
    path = attempt / "receipts" / ("%s-%d.json" % (kind, rank))
    atomic_json(path, value, immutable=kind in {"loaded", "completed"})
    return value


def receipt_matches(value, context, kind):
    return (value.get("kind") == kind and all(value.get(k) == context.get(k) for k in
            ("attempt_id", "run_id", "job_id", "binding_sha256", "checkpoint_sha256"))
            and type(value.get("rank")) is int and 0 <= value["rank"] < context["world_size"]
            and type(value.get("step")) is int and value["step"] >= 0)


def observe_receipts(attempt, context, cache=None):
    receipts = {kind: {} for kind in ("loaded", "progress", "completed", "signal_ack", "signal_delivered")}
    directory = Path(attempt) / "receipts"
    if directory.exists():
        for path in directory.iterdir():
            if not re.fullmatch(r"(?:loaded|progress|completed|signal_ack|signal_delivered)-[0-9]+\.json", path.name):
                continue
            stamp = path.stat()
            stamp = (stamp.st_ino, stamp.st_size, stamp.st_mtime_ns, stamp.st_ctime_ns)
            cached = cache.get(path.name) if cache is not None else None
            value = cached[1] if cached is not None and cached[0] == stamp else read_json(path, 8192)
            if cache is not None:
                cache[path.name] = (stamp, value)
            kind = value.get("kind")
            if kind in receipts and receipt_matches(value, context, kind) and path.name == "%s-%d.json" % (kind, value["rank"]):
                receipts[kind][value["rank"]] = value
    world = context["world_size"]
    step = context.get("checkpoint_step")
    loaded = {r for r, v in receipts["loaded"].items() if step is not None and v["step"] == step}
    progressed = {r for r, v in receipts["progress"].items() if r in loaded and v["step"] > step}
    complete_steps = {v["step"] for v in receipts["completed"].values()}
    completed = len(receipts["completed"]) == world and len(complete_steps) == 1 and all(
        value["step"] >= max(step or 0, receipts["progress"].get(rank, {}).get("step", 0))
        for rank, value in receipts["completed"].items())
    return {"loaded_ranks": len(loaded), "progressed_ranks": len(progressed),
            "missing_loaded_ranks": [r for r in range(world) if r not in loaded][:20],
            "resume_validated": step is not None and len(progressed) == world,
            "application_completion_observed": completed,
            "completed_step": next(iter(complete_steps)) if completed else None,
            "receipts": receipts}


def main(argv=None):
    """Passerelle JSON/CLI pour C, C++, Fortran et autres langages."""
    import argparse
    parser = argparse.ArgumentParser(description="Protocole generique ROMEO")
    actions = parser.add_subparsers(dest="action", required=True)
    event = actions.add_parser("event")
    event.add_argument("kind", choices=("loaded", "progress", "completed", "signal_ack"))
    event.add_argument("step", type=int)
    event.add_argument("--rank", type=int, default=None)
    publication = actions.add_parser("publish")
    publication.add_argument("request_file")
    arguments = parser.parse_args(argv)
    if arguments.action == "event":
        print(json.dumps(record_event(arguments.kind, arguments.step, rank=arguments.rank)))
    else:
        request = read_json(arguments.request_file)
        if set(request) != {"generation", "step", "files", "rank_steps"}:
            raise ValueError("Publication : generation, step, files et rank_steps sont obligatoires")
        context = application_context()
        signal_path = Path(os.environ["ROMEO_CHECKPOINT_ATTEMPT"]) / "signal.json"
        signal_id = read_json(signal_path)["request_id"] if signal_path.exists() else None
        path = publish(os.environ["ROMEO_CHECKPOINT_DIR"], context["run_id"], request["generation"], request["step"],
                       context["world_size"], request["files"], request["rank_steps"], context["binding"], signal_request_id=signal_id)
        print(json.dumps({"manifest_path": path, "published": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
