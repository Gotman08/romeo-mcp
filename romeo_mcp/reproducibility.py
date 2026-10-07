"""Fiches privees de reproductibilite, sans execution du script du job."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import uuid

from . import __version__
from .guard import check_path
from .privacy import redact_text, sanitize, sensitive_path
from .registry import registry
from .ssh import SSHError, SSHTimeout, session


MAX_DATA_FILES = 20
MAX_HASH_BYTES = 64 * 1024 * 1024
# Ce programme ne lit que des fichiers explicitement choisis. Aucun env/pip
# freeze ni remote Git : ces sources peuvent contenir des identifiants.
_PROBE = r'''
import hashlib, json, os, pathlib, re, stat, subprocess, sys
params = json.loads(sys.argv[1])
roots = [pathlib.Path(p).resolve() for p in params['roots']]
if params.get('include_home'):
    roots.append(pathlib.Path.home().resolve())
def allowed(value):
    path = pathlib.Path(value).resolve()
    if not any(path == root or root in path.parents for root in roots):
        raise ValueError('outside_roots')
    if any(p.lower().startswith(('.env', 'id_rsa', 'id_ed25519', 'id_ecdsa')) or p.lower() in ('.ssh', '.aws', '.azure', '.kube', 'hosts.yml')
           or p.lower().endswith(('.pem', '.key', '.p12', '.pfx'))
           or re.search(r'password|passwd|passphrase|secret|token|credential|authorization|cookie|api[_-]?key|access[_-]?key|private[_-]?key', p, re.I)
           for p in path.parts):
        raise ValueError('sensitive_path')
    return path
out = {'git': {'status': 'unavailable'}, 'data': []}
try:
    code = allowed(params['code_dir'])
    result = subprocess.run(['git', '-c', 'core.fsmonitor=false', '-C', str(code),
                             'rev-parse', '--verify', 'HEAD'],
                            capture_output=True, text=True, timeout=5,
                            env={**os.environ, 'GIT_OPTIONAL_LOCKS': '0'})
    sha = result.stdout.strip()
    if result.returncode == 0 and len(sha) in (40, 64) and all(c in '0123456789abcdef' for c in sha):
        out['git'] = {'status': 'observed', 'commit': sha, 'working_tree_verified': False}
except (OSError, ValueError, subprocess.TimeoutExpired):
    pass
remaining = params['max_bytes']
for name in params['data_files']:
    item = {'path': name}
    try:
        path = allowed(name)
        info = path.stat()
        if not stat.S_ISREG(info.st_mode):
            item['status'] = 'not_regular_file'
        elif info.st_size > remaining:
            item.update(status='size_limit', bytes=info.st_size)
        else:
            h = hashlib.sha256()
            consumed = 0
            with path.open('rb') as stream:
                while True:
                    block = stream.read(min(1048576, remaining - consumed + 1))
                    if not block:
                        break
                    consumed += len(block)
                    if consumed > remaining:
                        break
                    h.update(block)
            after = path.stat()
            remaining = max(0, remaining - consumed)
            if consumed != info.st_size or (info.st_size, info.st_mtime_ns, info.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
                item['status'] = 'changed_during_read'
            else:
                item.update(status='hashed', sha256=h.hexdigest(), bytes=consumed)
    except (OSError, ValueError):
        item['status'] = 'unreadable_or_outside_roots'
    out['data'].append(item)
print(json.dumps(out))
'''


_CAPTURE = r'''
import datetime, platform
out['observed_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
out['phase'] = 'before_workload'
out['environment'] = {
    'source': 'compute_node_before_command', 'architecture': platform.machine(),
    'python_version': platform.python_version(),
    'loaded_modules': [v for v in os.environ.get('LOADEDMODULES', '').split(':') if v][:128],
    'spack_loaded_hashes': [v for v in os.environ.get('SPACK_LOADED_HASHES', '').split(':') if v][:128],
}
jid = os.environ.get('SLURM_JOB_ID', '')
if os.environ.get('SLURM_ARRAY_JOB_ID') and os.environ.get('SLURM_ARRAY_TASK_ID'):
    jid = os.environ['SLURM_ARRAY_JOB_ID'] + '_' + os.environ['SLURM_ARRAY_TASK_ID']
if not re.fullmatch(r'[0-9]+(?:_[0-9]+)?', jid):
    raise ValueError('missing_job_id')
out['job_id'] = jid
folder = pathlib.Path('.romeo-provenance')
folder.mkdir(mode=0o700, exist_ok=True)
if folder.is_symlink():
    raise ValueError('symlink_capture_directory')
out['restart_count'] = os.environ.get('SLURM_RESTART_COUNT', '0')
try:
    fd = os.open(folder / (jid + '.json'), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    pass
else:
    with os.fdopen(fd, 'w') as stream:
        json.dump(out, stream)
        stream.write('\n')
'''


def runtime_fragment(workdir: str, scratch: str, data_files: list[str]) -> list[str]:
    """Releve borne sur le noeud alloue ; une panne de capture reste non fatale."""
    params = {"roots": [scratch, "/project"], "include_home": True, "code_dir": workdir,
              "data_files": data_files, "max_bytes": MAX_HASH_BYTES}
    program = _PROBE.replace("print(json.dumps(out))", "") + _CAPTURE
    return ["", "# Provenance du premier demarrage : environnement, commit et fichiers choisis.",
            "if command -v python3 >/dev/null 2>&1 && command -v timeout >/dev/null 2>&1; then",
            "  if timeout 20s python3 -I -S - {} <<'ROMEO_REPRO_CAPTURE'".format(shlex.quote(json.dumps(params))),
            program.rstrip(), "ROMEO_REPRO_CAPTURE", "  then :; else",
            "    printf '%s\\n' '[romeo-mcp] provenance indisponible ; le calcul continue.' >&2",
            "  fi", "fi", ""]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _observation(data: dict) -> dict:
    """Ne conserver que les champs du format, meme si le fichier a ete edite."""
    if not isinstance(data, dict) or not isinstance(data.get("git"), dict) or not isinstance(data.get("data"), list):
        raise ValueError("Releve de provenance invalide.")
    git = {"status": "unavailable"}
    commit = data["git"].get("commit", "")
    if data["git"].get("status") == "observed" and isinstance(commit, str) and re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", commit):
        git = {"status": "observed", "commit": commit, "working_tree_verified": False}
    entries = []
    if len(data["data"]) > MAX_DATA_FILES:
        raise ValueError("Releve de provenance trop volumineux.")
    for item in data["data"]:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ValueError("Empreinte invalide.")
        status = item.get("status")
        if status not in {"hashed", "size_limit", "not_regular_file", "changed_during_read", "unreadable_or_outside_roots"}:
            raise ValueError("Etat d'empreinte invalide.")
        entry = {"path": item["path"], "status": status}
        if status == "hashed":
            sha = item.get("sha256", "")
            if not isinstance(sha, str) or not re.fullmatch(r"[a-f0-9]{64}", sha):
                raise ValueError("SHA-256 invalide.")
            entry["sha256"] = sha
        size = item.get("bytes")
        if isinstance(size, int) and size >= 0:
            entry["bytes"] = size
        entries.append(entry)
    return {"git": git, "data": entries}


def _runtime_observation(data: dict, job_id: str) -> dict:
    out = _observation(data)
    if data.get("phase") != "before_workload" or data.get("job_id") != job_id:
        raise ValueError("Capture d'un autre job ou phase inconnue.")
    out.update(job_id=job_id, phase="before_workload", observed_at=str(data.get("observed_at", "")),
               restart_count=str(data.get("restart_count", "0")))
    env = data.get("environment", {})
    if not isinstance(env, dict):
        raise ValueError("Environnement de capture invalide.")
    out["environment"] = {k: env[k] for k in ("source", "architecture", "python_version")
                          if isinstance(env.get(k), str)}
    for key in ("loaded_modules", "spack_loaded_hashes"):
        values = env.get(key, [])
        if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
            raise ValueError("Liste d'environnements invalide.")
        out["environment"][key] = values[:128]
    return out


def observe_files(connection, code_dir: str, data_files: list[str]) -> dict:
    if len(data_files) > MAX_DATA_FILES:
        raise ValueError("Au plus 20 fichiers explicites peuvent etre empreintes par fiche.")
    roots = [connection.home, connection.scratch, *connection.path_aliases, "/project"]
    normalized = []
    for name in [code_dir, *data_files]:
        if not name or sensitive_path(name):
            raise ValueError("Chemin absent ou sensible : choisir uniquement du code ou des donnees scientifiques.")
        normalized.append(check_path(name, connection.home, connection.scratch, connection.path_aliases))
    params = {"roots": roots, "code_dir": normalized[0], "data_files": normalized[1:], "max_bytes": MAX_HASH_BYTES}
    result = connection.run("timeout 25s python3 -I -S -c {} {}".format(shlex.quote(_PROBE), shlex.quote(json.dumps(params))),
                            timeout=30, max_chars=20000)
    if not result.ok or result.truncated:
        raise SSHError("Releve du code et des donnees indisponible ou incomplet.")
    data = _observation(json.loads(result.stdout))
    return {**data, "observed_at": now(), "hash_budget_bytes": MAX_HASH_BYTES}


def submission_provenance(connection, plan) -> dict:
    """Un echec du releve ne doit pas empecher la soumission."""
    spec = plan.spec
    result = {"captured_at": now(), "phase": "before_submission", "mcp_version": __version__,
              "environment": {"source": "declared_in_job_spec", "modules": spec.modules,
                              "spack_packages": spec.spack_packages, "container": spec.container,
                              "architecture": plan.arch, "distributed": spec.distributed},
              "requested_resources": {"nodes": spec.nodes, "ntasks_per_node": spec.ntasks_per_node,
                                      "cpus_per_task": spec.cpus_per_task, "gpus_per_node": spec.gpus_per_node,
                                      "mem_gb": spec.mem_gb, "seconds": plan.seconds,
                                      "partition": plan.partition}}
    if spec.checkpoint_contract is not None or spec.mpi_environment is not None:
        from dataclasses import asdict
        result["checkpoint_job"] = {"spec": asdict(spec), "architecture": plan.arch,
                                    "target": {"host": getattr(connection, "host", ""),
                                               "user": getattr(connection, "user", ""), "account": spec.account}}
    try:
        result["code"] = observe_files(connection, plan.workdir, [])["git"]
    except (SSHError, SSHTimeout, ValueError, OSError):
        result["code"] = {"status": "unavailable"}
    return sanitize(result)


def _markdown(report: dict) -> str:
    script = report["script"]["content"]
    # Indentation plutot que fences : le texte du script ne peut pas fermer
    # son bloc pour injecter une image ou une consigne dans le document.
    details = json.dumps({k: v for k, v in report.items() if k != "script"}, ensure_ascii=False, indent=2)
    return ("# Fiche de reproductibilite ROMEO\n\n"
            "Les dates et sources distinguent la soumission du releve apres coup.\n\n"
            "## Informations et limites\n\n" + "\n".join("    " + line for line in details.splitlines()) +
            "\n\n## Script Slurm filtre\n\n" + "\n".join("    " + line for line in script.splitlines()) + "\n")


def collect_report(job_id: str, *, code_dir: str = "",
                  data_files: list[str] | None = None, live: bool = True,
                  connection=None, job_registry=None) -> dict:
    if not re.fullmatch(r"[0-9]+(?:_[0-9]+)?", job_id):
        raise ValueError("Identifiant Slurm invalide : nombre, ou nombre_indice pour un tableau.")
    data_files = data_files or []
    if len(data_files) > MAX_DATA_FILES or any(sensitive_path(p) for p in data_files):
        raise ValueError("Choisir au plus 20 fichiers scientifiques, sans fichier de secrets.")
    store = job_registry or registry()
    record = store.get(job_id) or store.get(job_id.split("_")[0])
    if record is None:
        raise ValueError("Job absent du registre local. La fiche exige le script conserve lors d'une soumission par ce MCP.")
    original_script = record.get("script") or ""
    script = redact_text(original_script)
    provenance = store.get_provenance(record["job_id"])
    missing = []
    if provenance is None:
        missing.append("Ce job ancien n'a pas de provenance enregistree a la soumission.")
    report = {"schema_version": 1, "job_id": job_id, "created_at": now(), "mcp_version": __version__,
              "submission": provenance, "script": {"source": "local_job_registry", "content": script,
                "redacted": script != original_script, "exported_sha256": hashlib.sha256(script.encode()).hexdigest()},
              "observations": None, "resource_usage": [], "missing_information": missing,
              "runtime": None, "resource_usage_observed_at": None,
              "limits": ["La capture sur le noeud precede la commande : un environnement active par cette commande peut ensuite differer.",
                         "Un commit Git ne prouve pas l'absence de modifications locales ni le contenu des fichiers non suivis.",
                         "Les empreintes collectees au releve decrivent les fichiers a cette date, pas necessairement les entrees originales.",
                         "Une revue du contenu reste necessaire pour les valeurs opaques sans marqueur."]}
    if live:
        connection = connection or session()
        try:
            directory = check_path(record["workdir"], connection.home, connection.scratch, connection.path_aliases)
            capture_path = directory.rstrip("/") + "/.romeo-provenance/" + job_id + ".json"
            # Une fin sans LF ne doit pas absorber le marqueur du transport SSH.
            # Borne aussi la lecture si un fichier de capture a ete remplace.
            command = "head -c 24001 -- {}; romeo_read_rc=$?; printf '\\n'; exit \"$romeo_read_rc\"".format(shlex.quote(capture_path))
            capture = connection.run(command, timeout=10, max_chars=24000)
            if capture.ok and not capture.truncated:
                report["runtime"] = _runtime_observation(json.loads(capture.stdout), job_id)
            if report["runtime"] is None:
                missing.append("Capture sur le noeud absente : job ancien, en attente, ou capture indisponible.")
        except (SSHError, SSHTimeout, ValueError, OSError):
            missing.append("Capture sur le noeud non accessible.")
        try:
            report["observations"] = observe_files(connection, code_dir or record["workdir"], data_files)
        except (SSHError, SSHTimeout, ValueError, OSError):
            missing.append("Code et empreintes non releves : verifier les chemins, SSH et Python 3 distant.")
        # JobID conserve racine_indice pour les tableaux, contrairement a JobIDRaw.
        fields = "JobID,User,State,Elapsed,TotalCPU,AllocCPUS,ReqMem,MaxRSS,AllocTRES,ExitCode,Submit,Start,End"
        try:
            result = connection.run("sacct -nP -j {} -o {}".format(shlex.quote(job_id), fields),
                                    timeout=30, max_chars=40000)
            if not result.ok or result.truncated:
                missing.append("Comptabilite Slurm indisponible ou tronquee.")
            else:
                owner = connection.user
                for line in result.stdout.splitlines():
                    parts = line.strip().split("|")
                    if len(parts) >= 13:
                        row = dict(zip(fields.split(","), parts))
                        if row["JobID"].split(".")[0] == job_id and row["User"] in {owner, ""}:
                            row.pop("User")
                            report["resource_usage"].append(row)
                report["resource_usage_observed_at"] = now()
                if not report["resource_usage"]:
                    missing.append("Aucune comptabilite du job trouvee pour cet utilisateur.")
        except (SSHError, SSHTimeout):
            missing.append("Lecture de la comptabilite Slurm impossible.")
    else:
        missing.append("Releve local : aucun etat Slurm ni fichier distant n'a ete relu.")
    if not data_files and not (report["runtime"] or {}).get("data"):
        missing.append("Aucun fichier de donnees selectionne pour empreinte.")
    report = sanitize(report)
    return {"ok": True, **store.save_report(report), "missing_information": report["missing_information"]}


def report_get(report_id: str, *, job_registry=None) -> dict:
    saved = (job_registry or registry()).get_report(report_id)
    if saved is None:
        raise ValueError("Releve introuvable.")
    return {"ok": True, **saved}


def export_snapshot(report_id: str, *, output_dir: str = "", job_registry=None) -> dict:
    saved = report_get(report_id, job_registry=job_registry)
    report = saved["report"]
    job_id = report["job_id"]
    destination = Path(output_dir).expanduser() if output_dir else Path.home() / ".romeo-mcp" / "reports"
    destination = destination.resolve()
    if any((p / ".git").exists() for p in [destination, *destination.parents]):
        raise ValueError("Choisir un dossier d'export hors d'un depot Git pour proteger les donnees du job.")
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    folder = destination / ("job-{}-{}".format(job_id, uuid.uuid4().hex[:12]))
    folder.mkdir(mode=0o700)
    contents = {"report.json": json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                "report.md": _markdown(report), "script.sbatch.txt": report["script"]["content"]}
    for name, content in contents.items():
        fd = os.open(folder / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
    return {"ok": True, "report_id": report_id, "report_sha256": saved["report_sha256"],
            "created_at": report["created_at"], "job_id": job_id, "directory": str(folder),
            "files": {k: str(folder / k) for k in contents},
            "script_redacted": report["script"]["redacted"],
            "missing_information": report["missing_information"],
            "data_files_hashed": sum(f.get("status") == "hashed" for f in (report["observations"] or {}).get("data", [])),
            "runtime_data_files_hashed": sum(f.get("status") == "hashed" for f in (report["runtime"] or {}).get("data", []))}


def export_report(job_id: str, *, output_dir: str = "", code_dir: str = "",
                  data_files: list[str] | None = None, live: bool = True,
                  connection=None, job_registry=None) -> dict:
    """Parcours CLI historique : compose collecte et export, sans etre un outil MCP."""
    collected = collect_report(job_id, code_dir=code_dir, data_files=data_files, live=live,
                               connection=connection, job_registry=job_registry)
    return export_snapshot(collected["report_id"], output_dir=output_dir, job_registry=job_registry)
