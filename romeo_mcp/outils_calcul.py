"""Soumettre et suivre un calcul.

Jobs isoles, balayages parametriques, chaines de segments reprenables,
enchainements d'etapes dependantes, et choix du creneau de soumission.
"""

from __future__ import annotations

import hashlib
import posixpath
import shlex
import time
import uuid
from typing import Any
from .cluster import (
    ARCHS,
    ClusterError,
    DEFAULT_ACCOUNT,
    require_account,
    PARTITIONS,
    PARTITION_ORDER,
    format_slurm_time,
    parse_duration,
)
from .guard import GuardError, check_path
from .registry import registry
from .sortie import decouper, marqueur, nouveau_jeton
from .pipeline import clause_dependance, heriter, ordonner, valider_etapes
from .slurm import (
    JobSpec,
    TERMINAL_STATES,
    parse_pipe_table,
    plan_job,
    summarize_efficiency,
)
from .ssh import SSHError, SSHTimeout, session
from .outils_contexte import romeo_status
from .noyau import (
    MAX_WAIT_SECONDS,
    MUTATING,
    READ_ONLY,
    _NOM_ENCHAINEMENT,
    _contexte_chemins,
    _controle_du_script_genere,
    _doublon_recent,
    _error,
    _sh,
    _soumettre_sbatch,
    outil,
)


# =============================================================================
# Jobs
# =============================================================================
@outil(
    annotations=MUTATING,
    description=(
        "Prepare et soumet un job SLURM. `distributed='mpi'` couvre le "
        "calcul parallele courant (prefixe srun, avec ou sans GPU) ; les "
        "familles ddp, accelerate, deepspeed et srun sont propres a "
        "PyTorch et ajoutent son point de rendez-vous. Options : "
        "`container` pour une image Apptainer, `redirect_caches` pour "
        "detourner les caches Python hors du home, `stage_archive` pour "
        "mettre un jeu de donnees en memoire vive. `data_files` choisit les "
        "entrees a empreinter au demarrage pour export_job_report (20 fichiers, 64 Mio). En simulation par "
        "defaut : rend le "
        "script sbatch genere, la partition et l'architecture deduites, et les "
        "avertissements de dimensionnement, SANS rien soumettre. Relance avec "
        "confirm=true pour soumettre reellement. La partition est deduite du "
        "temps demande et l'architecture du besoin en GPU : ne les force que si "
        "tu as une raison precise."
    ),
)
def submit_job(
    name: str,
    command: str,
    time_limit: str = "1h",
    nodes: int = 1,
    ntasks_per_node: int = 1,
    cpus_per_task: int = 1,
    gpus_per_node: int = 0,
    mem_gb: int | None = None,
    arch: str | None = None,
    partition: str | None = None,
    modules: list[str] | None = None,
    spack_packages: list[str] | None = None,
    workdir: str | None = None,
    array: str | None = None,
    distributed: str | None = None,
    container: str | None = None,
    redirect_caches: bool = False,
    nccl_debug: bool = False,
    stage_archive: str | None = None,
    job_tmpdir: bool = False,
    keep_patterns: list[str] | None = None,
    cpu_bind: str | None = None,
    secret_env_file: str | None = None,
    data_files: list[str] | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Valide une intention de calcul, puis la soumet si `confirm` est vrai."""
    require_account()
    s = session()
    spec = JobSpec(
        name=name,
        command=command,
        time=time_limit,
        nodes=nodes,
        ntasks_per_node=ntasks_per_node,
        cpus_per_task=cpus_per_task,
        gpus_per_node=gpus_per_node,
        mem_gb=mem_gb,
        arch=arch,
        partition=partition,
        modules=modules or [],
        spack_packages=spack_packages or [],
        workdir=workdir,
        array=array,
        distributed=distributed,
        container=container,
        redirect_caches=redirect_caches,
        nccl_debug=nccl_debug,
        stage_archive=stage_archive,
        job_tmpdir=job_tmpdir,
        keep_patterns=keep_patterns or [],
        cpu_bind=cpu_bind,
        secret_env_file=secret_env_file,
        data_files=data_files or [],
    )

    try:
        foyer, racine, alias, hors_ligne = _contexte_chemins(s, confirm)
        if workdir:
            spec.workdir = check_path(workdir, foyer, racine, alias)
        plan = plan_job(spec, racine)
    except (ClusterError, GuardError) as exc:
        return _error(str(exc))
    except (SSHError, SSHTimeout) as exc:
        return _error(str(exc))
    avertissements = list(plan.warnings)
    if hors_ligne:
        avertissements.insert(0, hors_ligne)

    resolved = {
        "partition": plan.partition,
        "arch": plan.arch,
        "constraint": ARCHS[plan.arch]["feature"],
        "target_nodes": ARCHS[plan.arch]["nodes"],
        "time": format_slurm_time(plan.seconds),
        "total_cpus": plan.total_cpus,
        "total_gpus": plan.total_gpus,
        "workdir": plan.workdir,
        "account": plan.spec.account,
        "distributed": plan.spec.distributed,
        "container": plan.spec.container,
        "redirect_caches": plan.spec.redirect_caches,
        "ntasks_per_node": plan.spec.ntasks_per_node,
        "mem_gb": plan.spec.mem_gb,
    }

    if not confirm:
        return {
            "ok": True,
            "submitted": False,
            "mode": "simulation",
            "resolved": resolved,
            "warnings": avertissements,
            "script": plan.script,
            "next_step": (
                "Relis le script et les avertissements, puis rappelle submit_job "
                "avec des parametres identiques et confirm=true pour soumettre."
            ),
        }

    precedent = _doublon_recent(plan.script)
    if precedent:
        return _error(
            "job identique deja soumis il y a {} s (job {}, etat {}). Rien n'a "
            "ete soumis. Si la repetition est voulue, change le nom du job ou "
            "attends la fin du precedent ; sinon suis-le avec job_status.".format(
                int(time.time() - precedent["submitted_at"]),
                precedent["job_id"], precedent.get("last_state") or "soumis"),
            duplicate_of=precedent["job_id"],
        )

    bloquants = _controle_du_script_genere(plan.script)
    if bloquants:
        return _error(
            "le script genere ne passe pas le controle du serveur lui-meme : "
            "{}. Rien n'a ete soumis -- c'est une anomalie du gabarit, pas de "
            "ta demande.".format(" ; ".join(bloquants)),
            inattendu=True,
        )

    soumission = _soumettre_sbatch(s, plan, spec.name)
    if not soumission["ok"]:
        return soumission
    job_id = soumission["job_id"]

    return {
        "ok": True,
        "submitted": True,
        "job_id": job_id,
        "resolved": resolved,
        "warnings": plan.warnings,
        "script_path": soumission["script_path"],
        "stdout": soumission["stdout"],
        "stderr": soumission["stderr"],
        "next_step": (
            "Le job est en file. Consulte job_status('{}') ; ne bloque pas en "
            "attente, reviens plus tard.".format(job_id)
        ),
    }

@outil(
    annotations=READ_ONLY,
    description=(
        "Etat d'un job : file d'attente puis historique si le job est termine. "
        "Inclut le demarrage estime pour un job en attente."
    ),
)
def job_status(job_id: str) -> dict[str, Any]:
    """Interroge squeue, avec repli sur sacct pour les jobs termines."""
    s = session()
    jid = str(job_id).strip()
    command = (
        "echo '###LIVE'; squeue -h -j {jid} -o '%i|%j|%P|%T|%M|%L|%D|%R' 2>/dev/null; "
        "echo '###START'; squeue -h -j {jid} --start -o '%S' 2>/dev/null; "
        "echo '###PAST'; sacct -j {jid} -X -n -P "
        "-o JobID,JobName,Partition,State,Elapsed,ExitCode,Start,End 2>/dev/null"
    ).format(jid=shlex.quote(jid))

    try:
        result = _sh(s, command, timeout=40, max_chars=10_000)
    except (SSHError, SSHTimeout) as exc:
        return _error(str(exc))

    sections: dict[str, list[str]] = {}
    current = None
    for line in result.stdout.splitlines():
        if line.startswith("###"):
            current = line[3:].strip()
            sections[current] = []
        elif current and line.strip():
            sections[current].append(line.strip())

    live = sections.get("LIVE", [])
    if live:
        parts = live[0].split("|")
        state = parts[3].strip() if len(parts) > 3 else "?"
        start = sections.get("START", [""])[0] if sections.get("START") else ""
        registry().set_state(jid, state)
        return {
            "ok": True,
            "job_id": jid,
            "finished": False,
            "name": parts[1].strip() if len(parts) > 1 else "",
            "partition": parts[2].strip() if len(parts) > 2 else "",
            "state": state,
            "elapsed": parts[4].strip() if len(parts) > 4 else "",
            "remaining": parts[5].strip() if len(parts) > 5 else "",
            "nodes": parts[6].strip() if len(parts) > 6 else "",
            "reason_or_nodelist": parts[7].strip() if len(parts) > 7 else "",
            "estimated_start": start or None,
        }

    past = sections.get("PAST", [])
    if past:
        parts = past[0].split("|")
        state = parts[3].strip() if len(parts) > 3 else "?"
        registry().set_state(jid, state)
        return {
            "ok": True,
            "job_id": jid,
            "finished": state.split()[0] in TERMINAL_STATES,
            "name": parts[1].strip() if len(parts) > 1 else "",
            "partition": parts[2].strip() if len(parts) > 2 else "",
            "state": state,
            "elapsed": parts[4].strip() if len(parts) > 4 else "",
            "exit_code": parts[5].strip() if len(parts) > 5 else "",
            "start": parts[6].strip() if len(parts) > 6 else "",
            "end": parts[7].strip() if len(parts) > 7 else "",
            "next_step": "Consulte job_output puis job_efficiency.",
        }

    return _error(
        "job {} inconnu de SLURM. Verifie l'identifiant, ou l'historique a "
        "peut-etre ete purge.".format(jid),
        job_id=jid,
    )

@outil(
    annotations=READ_ONLY,
    description=(
        "Sortie d'un job, tronquee par defaut. N'affiche JAMAIS un log entier : "
        "utilise `lines` pour la fin du fichier et `grep` pour cibler. Le mode "
        "stream='auto' privilegie les extraits stderr non blancs apres filtre. "
        "has_stderr_content indique la presence d'octets dans les fichiers "
        "stderr, independamment du filtre et du flux affiche."
    ),
)
def job_output(
    job_id: str,
    stream: str = "auto",
    lines: int = 60,
    grep: str | None = None,
    max_chars: int = 8000,
) -> dict[str, Any]:
    """Lit la fin des fichiers de sortie d'un job."""
    s = session()
    jid = str(job_id).strip()
    lines = max(1, min(int(lines), 500))

    record = registry().get(jid)
    if record:
        out_glob, err_glob = record["stdout_glob"], record["stderr_glob"]
    else:
        # Job soumis hors de ce serveur : on demande les chemins a SLURM.
        try:
            info = _sh(
                s,
                "scontrol show job {} 2>/dev/null | tr ' ' '\\n' | "
                "grep -E '^(StdOut|StdErr)=' ".format(shlex.quote(jid)),
                timeout=30,
            )
        except (SSHError, SSHTimeout) as exc:
            return _error(str(exc))
        paths = dict(
            item.split("=", 1) for item in info.stdout.split() if "=" in item
        )
        out_glob = paths.get("StdOut")
        err_glob = paths.get("StdErr")
        if not out_glob:
            return _error(
                "chemins de log introuvables pour le job {}. Il n'a pas ete "
                "soumis par ce serveur et SLURM ne le connait plus.".format(jid)
            )

    targets = {}
    for label, glob in (("err", err_glob), ("out", out_glob)):
        if not glob:
            continue
        # Quoter le repertoire tout en laissant le motif s'etendre.
        dossier = posixpath.dirname(glob)
        motif = posixpath.basename(glob)
        targets[label] = "{}/{}".format(shlex.quote(dossier), motif) if dossier else motif
    if stream in ("out", "err"):
        wanted = [stream]
    elif stream == "both":
        wanted = ["err", "out"]
    else:  # auto : l'erreur d'abord si elle contient quelque chose
        wanted = ["err", "out"]

    filter_cmd = (
        "grep -E -- {} ".format(shlex.quote(grep)) if grep else "cat"
    )
    # Seul outil a voir du texte utilisateur arbitraire : un journal contenant
    # `### Validation ###` ou une banniere `##########` creait des sections
    # parasites et faisait disparaitre la fin du journal, precisement la trace
    # d'erreur recherchee. D'ou un marqueur a jeton, que le journal deja ecrit
    # ne peut pas contenir.
    jeton = nouveau_jeton()
    parts = []
    if "err" in targets:
        # Sonder les fichiers avant tout extrait : ni les en-tetes, ni grep,
        # ni le budget d'affichage ne doivent changer cet indicateur.
        parts.append(
            "echo '{marqueur}'; for f in {cible}; do "
            'if [ -f "$f" ] && [ -s "$f" ]; then echo 1; break; fi; done'.format(
                marqueur=marqueur(jeton, "stderr_nonempty"), cible=targets["err"],
            )
        )
    for label in wanted:
        if label not in targets:
            continue
        # Une section par fichier : la premiere ligne porte le chemin, les
        # suivantes uniquement le contenu. Ajouter les en-tetes cote Python.
        parts.append(
            'romeo_log_index=0; for f in {cible}; do [ -f "$f" ] || continue; '
            'printf \'%s\\n\' "{marqueur}_$romeo_log_index" "$f"; '
            '{filt} "$f" | tail -n {n}; printf \'\\n\'; '
            'romeo_log_index=$((romeo_log_index + 1)); done'.format(
                marqueur=marqueur(jeton, label), cible=targets[label],
                filt=filter_cmd, n=lines,
            )
        )

    try:
        result = _sh(
            s, "; ".join(parts), timeout=60, max_chars=max(max_chars * 2, 4000)
        )
    except (SSHError, SSHTimeout) as exc:
        return _error(str(exc))

    sections = decouper(result.stdout, jeton)
    logs = {"err": [], "out": []}
    for key, file_lines in sections.items():
        label = key.rpartition("_")[0]
        if label in logs and file_lines:
            payload = "\n".join(file_lines[1:]).rstrip()
            if payload.strip():
                logs[label].append("--- {}\n{}".format(file_lines[0], payload))
    err_text = "\n".join(logs["err"])
    out_text = "\n".join(logs["out"])

    if stream == "auto":
        chosen = "err" if err_text else "out"
        body = err_text or out_text
    elif stream == "both":
        chosen = "both"
        body = "=== stderr ===\n{}\n\n=== stdout ===\n{}".format(err_text, out_text)
    else:
        chosen = stream
        body = err_text if stream == "err" else out_text

    if len(body) > max_chars:
        body = "[... debut tronque ...]\n" + body[-max_chars:]

    return {
        "ok": True,
        "job_id": jid,
        "stream": chosen,
        "lines_requested": lines,
        "grep": grep,
        "has_stderr_content": "1" in sections.get("stderr_nonempty", []),
        "content": body or "(aucune sortie pour l'instant)",
    }

@outil(
    annotations=READ_ONLY,
    description=(
        "Efficacite reelle d'un job termine : CPU, memoire, GPU alloues, plus "
        "des recommandations de redimensionnement. Remplace `seff`, absent de "
        "ROMEO. A lire systematiquement apres un job pour calibrer le suivant."
    ),
)
def job_efficiency(job_id: str) -> dict[str, Any]:
    """Recalcule les metriques de seff depuis sacct."""
    s = session()
    jid = str(job_id).strip()
    command = (
        "sacct -j {} -P -o "
        "JobID,JobName,Partition,State,ExitCode,Elapsed,TotalCPU,AllocCPUS,"
        "ReqMem,MaxRSS,AllocTRES 2>/dev/null".format(shlex.quote(jid))
    )
    try:
        result = _sh(s, command, timeout=45, max_chars=20_000)
    except (SSHError, SSHTimeout) as exc:
        return _error(str(exc))

    rows = parse_pipe_table(result.stdout)
    summary = summarize_efficiency(rows, jid)
    if not summary.get("found"):
        return _error(
            "aucune donnee de comptabilite pour le job {}. Il est peut-etre "
            "encore en file, ou trop ancien.".format(jid),
            job_id=jid,
        )
    summary["ok"] = True
    return summary

@outil(
    annotations=MUTATING,
    description="Annule un job en file ou en cours.",
)
def cancel_job(job_id: str) -> dict[str, Any]:
    """Annule un job. Operation reversible dans le sens ou rien n'est efface."""
    s = session()
    jid = str(job_id).strip()
    if not jid.replace("_", "").replace("[", "").replace("]", "").isdigit():
        return _error("identifiant de job invalide : {!r}".format(job_id))
    try:
        result = _sh(s, "scancel {}".format(shlex.quote(jid)), timeout=30)
    except (SSHError, SSHTimeout) as exc:
        return _error(str(exc))
    if not result.ok:
        return _error("scancel a echoue : {}".format(result.stdout.strip()))
    registry().set_state(jid, "CANCELLED")
    return {"ok": True, "job_id": jid, "cancelled": True}

@outil(
    annotations=READ_ONLY,
    description=(
        "Tes jobs : ceux en file cote SLURM, et ceux soumis via ce serveur "
        "(avec leur repertoire de travail et le chemin de leurs logs, meme "
        "apres une perte de contexte)."
    ),
)
def list_jobs(limit: int = 15) -> dict[str, Any]:
    """Vue combinee de la file vivante et du registre local."""
    s = session()
    limit = max(1, min(int(limit), 50))
    try:
        result = _sh(
            s,
            "squeue -h -u $USER -o '%i|%j|%P|%T|%M|%L|%R'",
            timeout=35,
            max_chars=20_000,
        )
        live_rows = result.stdout.splitlines()
    except (SSHError, SSHTimeout) as exc:
        return _error(str(exc))

    live = []
    for line in live_rows:
        parts = line.split("|")
        if len(parts) >= 7:
            live.append(
                {
                    "job_id": parts[0].strip(),
                    "name": parts[1].strip(),
                    "partition": parts[2].strip(),
                    "state": parts[3].strip(),
                    "elapsed": parts[4].strip(),
                    "remaining": parts[5].strip(),
                    "reason_or_nodes": parts[6].strip(),
                }
            )

    known = []
    for record in registry().recent(limit):
        known.append(
            {
                "job_id": record["job_id"],
                "name": record["name"],
                "submitted_at": time.strftime(
                    "%Y-%m-%d %H:%M", time.localtime(record["submitted_at"])
                ),
                "partition": record["partition"],
                "arch": record["arch"],
                "workdir": record["workdir"],
                "last_known_state": record["last_state"],
            }
        )

    return {
        "ok": True,
        "in_queue": live,
        "submitted_via_mcp": known,
        "note": (
            "in_queue vient de SLURM ; submitted_via_mcp vient du registre "
            "local et survit a une perte de contexte."
        ),
    }

@outil(
    annotations=READ_ONLY,
    description=(
        "Attend qu'un job se termine, avec un plafond strict (600 s). Utilise-le "
        "seulement pour un job court : sinon reviens interroger job_status."
    ),
)
def wait_for_job(job_id: str, timeout_seconds: int = 120, poll_seconds: int = 10) -> dict[str, Any]:
    """Sondage borne. Ne sequestre jamais le modele plus de MAX_WAIT_SECONDS."""
    jid = str(job_id).strip()
    budget = max(10, min(int(timeout_seconds), MAX_WAIT_SECONDS))
    interval = max(5, min(int(poll_seconds), 60))
    deadline = time.monotonic() + budget

    last: dict = {}
    while time.monotonic() < deadline:
        last = job_status(jid)
        if not last.get("ok"):
            return last
        if last.get("finished"):
            last["waited_seconds"] = round(budget - (deadline - time.monotonic()), 1)
            return last
        time.sleep(min(interval, max(1, deadline - time.monotonic())))

    last["ok"] = True
    last["timed_out"] = True
    last["note"] = (
        "le job tourne toujours apres {} s d'attente. Ce n'est pas une erreur : "
        "reviens interroger job_status plus tard.".format(budget)
    )
    return last

# =============================================================================
# Balayages parametriques
# =============================================================================
@outil(
    annotations=MUTATING,
    description=(
        "Soumet un balayage parametrique en tableau SLURM : une tache par jeu "
        "de parametres, avec un plafond de taches simultanees. Chaque tache "
        "recoit sa ligne de parametres dans la variable $PARAMS, que ta "
        "commande peut interpoler. Ideal pour une recherche d'hyperparametres "
        "ou une evaluation sur plusieurs jeux de donnees. Simulation par "
        "defaut, comme submit_job."
    ),
)
def submit_array_job(
    name: str,
    command: str,
    parameters: list[str],
    max_concurrent: int = 4,
    time_limit: str = "1h",
    cpus_per_task: int = 1,
    gpus_per_node: int = 0,
    mem_gb: int | None = None,
    arch: str | None = None,
    modules: list[str] | None = None,
    spack_packages: list[str] | None = None,
    workdir: str | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Genere un tableau SLURM pilote par un fichier de parametres."""
    require_account()
    s = session()
    if not parameters:
        return _error("aucun jeu de parametres : le tableau serait vide.")
    if len(parameters) > 1000:
        return _error(
            "{} taches demandees : au-dela de 1000, decoupe en plusieurs "
            "tableaux.".format(len(parameters))
        )
    # La tache N lit la ligne N du fichier de parametres. Un element contenant
    # un saut de ligne decalerait toutes les taches suivantes, sans aucune
    # erreur : le balayage rendrait des resultats faux mais plausibles.
    fautifs = [
        index for index, valeur in enumerate(parameters)
        if "\n" in valeur or "\r" in valeur or not valeur.strip()
    ]
    if fautifs:
        return _error(
            "les jeux de parametres {} sont vides ou contiennent un saut de "
            "ligne. Chaque jeu doit tenir sur une ligne : la tache N lit la "
            "ligne N du fichier.".format(fautifs[:5])
        )
    max_concurrent = max(1, min(int(max_concurrent), len(parameters)))

    spec = JobSpec(
        name=name,
        command=command,
        time=time_limit,
        cpus_per_task=cpus_per_task,
        gpus_per_node=gpus_per_node,
        mem_gb=mem_gb,
        arch=arch,
        modules=modules or [],
        spack_packages=spack_packages or [],
        workdir=workdir,
        array="0-{}%{}".format(len(parameters) - 1, max_concurrent),
    )

    try:
        if workdir:
            spec.workdir = check_path(workdir, s.home, s.scratch, s.path_aliases)
        plan = plan_job(spec, s.scratch)
        # Resoudre d'abord le dossier, puis y reserver des noms propres a cet
        # appel. N tableaux peuvent ainsi partager le meme workdir et nom.
        submission_id = uuid.uuid4().hex
        params_path = posixpath.join(plan.workdir, "parametres-{}.txt".format(submission_id))
        script_path = posixpath.join(plan.workdir, "{}-{}.sbatch".format(name, submission_id))
        spec.command = (
            'PARAMS="$(sed -n "$((SLURM_ARRAY_TASK_ID + 1))p" {})"\n'
            'echo "[romeo-mcp] tache $SLURM_ARRAY_TASK_ID : $PARAMS"\n'
        ).format(shlex.quote(params_path)) + command
        plan = plan_job(spec, s.scratch)
    except (ClusterError, GuardError, SSHError, SSHTimeout) as exc:
        return _error(str(exc))

    resume = {
        "taches": len(parameters),
        "simultanees_max": max_concurrent,
        "partition": plan.partition,
        "arch": plan.arch,
        "workdir": plan.workdir,
        "array": spec.array,
    }

    if not confirm:
        return {
            "ok": True,
            "submitted": False,
            "mode": "simulation",
            "resolved": resume,
            "warnings": plan.warnings,
            "parameters_preview": parameters[:5],
            "script": plan.script,
            "next_step": "Rappelle avec confirm=true pour soumettre le tableau.",
        }

    # Le fichier de parametres doit exister avant la soumission : la tache 0
    # peut demarrer immediatement.
    parameters_text = "\n".join(parameters) + "\n"
    try:
        s.write_file(params_path, parameters_text, mode="400")
    except (SSHError, SSHTimeout) as exc:
        return _error(str(exc))

    soumission = _soumettre_sbatch(
        s, plan, spec.name, note="tableau de {} taches".format(len(parameters)),
        script_path=script_path,
        artifacts={"parameters": {
            "path": params_path,
            "source": "generated_content",
            "sha256": hashlib.sha256(parameters_text.encode("utf-8")).hexdigest(),
            "rows": len(parameters),
        }},
    )
    if not soumission["ok"]:
        return soumission
    return {
        "ok": True, "submitted": True, "job_id": soumission["job_id"],
        "resolved": resume, "warnings": plan.warnings,
        "parameters_file": params_path,
        "script_path": soumission["script_path"],
        "next_step": "Suis l'avancement avec job_status('{}').".format(
            soumission["job_id"]),
    }

# =============================================================================
# Resilience : chaine de segments reprenables
# =============================================================================
@outil(
    annotations=MUTATING,
    description=(
        "Soumet un calcul long sous forme de chaine de segments reprenables, "
        "pour depasser la limite de temps d'une partition rapide. Chaque "
        "segment recoit SIGUSR1 avant son expiration pour sauvegarder, et le "
        "suivant demarre apres lui via une dependance, en reprenant du dernier "
        "point de sauvegarde. Un marqueur de fin fait sauter les segments "
        "restants si le calcul se termine avant terme. Ton code doit savoir "
        "reprendre depuis checkpoint_dir et, idealement, traiter SIGUSR1."
    ),
)
def submit_resilient_job(
    name: str,
    command: str,
    segment_time: str = "1h",
    max_total_time: str = "6h",
    checkpoint_dir: str = "",
    signal_before: int = 300,
    cpus_per_task: int = 16,
    gpus_per_node: int = 1,
    mem_gb: int | None = None,
    arch: str | None = None,
    spack_packages: list[str] | None = None,
    stage_archive: str | None = None,
    workdir: str | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Chaine plusieurs segments dependants autour d'un point de reprise."""
    require_account()
    s = session()
    try:
        duree_segment = parse_duration(segment_time)
        duree_totale = parse_duration(max_total_time)
    except ClusterError as exc:
        return _error(str(exc))

    if duree_segment < 600:
        return _error(
            "un segment de moins de 10 minutes laisse trop peu de temps utile "
            "une fois le preavis de sauvegarde deduit."
        )
    if signal_before >= duree_segment:
        return _error(
            "le preavis ({} s) doit rester inferieur a la duree d'un segment "
            "({} s).".format(signal_before, duree_segment)
        )

    segments = max(1, -(-duree_totale // duree_segment))
    if segments > 20:
        return _error(
            "{} segments seraient necessaires : reduis max_total_time ou "
            "allonge segment_time.".format(segments)
        )

    dossier = checkpoint_dir or posixpath.join(s.scratch, "ckpts", name)
    try:
        dossier = check_path(dossier, s.home, s.scratch, s.path_aliases)
    except GuardError as exc:
        return _error(str(exc))

    spec = JobSpec(
        name=name, command=command, time=segment_time,
        cpus_per_task=cpus_per_task, gpus_per_node=gpus_per_node, mem_gb=mem_gb,
        arch=arch, spack_packages=spack_packages or [], workdir=workdir,
        checkpoint_dir=dossier, signal_before=int(signal_before),
        stage_archive=stage_archive,
    )
    try:
        if workdir:
            spec.workdir = check_path(workdir, s.home, s.scratch, s.path_aliases)
        plan = plan_job(spec, s.scratch)
    except (ClusterError, GuardError, SSHError, SSHTimeout) as exc:
        return _error(str(exc))

    resume = {
        "segments": segments,
        "duree_par_segment": format_slurm_time(duree_segment),
        "duree_cumulee": format_slurm_time(duree_segment * segments),
        "partition": plan.partition,
        "arch": plan.arch,
        "checkpoint_dir": dossier,
        "preavis_s": int(signal_before),
    }

    if not confirm:
        return {
            "ok": True, "submitted": False, "mode": "simulation",
            "resolved": resume, "warnings": plan.warnings, "script": plan.script,
            "prerequis": (
                "Ton programme doit (1) reprendre automatiquement depuis "
                "{} s'il y trouve un etat, et (2) sauvegarder en recevant "
                "SIGUSR1 ou en voyant apparaitre le fichier "
                "SAUVEGARDE_DEMANDEE.".format(dossier)
            ),
            "next_step": "Rappelle avec confirm=true pour soumettre la chaine.",
        }

    identifiants: list[str] = []
    precedent = None
    script_path = None
    for index in range(segments):
        options = ()
        if precedent:
            # `afterany` enchaine quel que soit le sort du segment precedent :
            # un depassement de temps est justement le cas nominal ici.
            options = ("--dependency=afterany:{}".format(precedent),)
        soumission = _soumettre_sbatch(
            s, plan, name,
            note="segment {}/{} de chaine reprenable".format(index + 1, segments),
            options=options,
            # Le script est identique pour tous les segments : on ne l'ecrit
            # qu'une fois, le reste de la chaine le reutilise.
            ecrire=(index == 0),
            script_path=script_path,
        )
        if not soumission["ok"]:
            # Les segments deja soumis existent sur le cluster : les taire
            # laisserait des jobs orphelins que personne ne penserait a annuler.
            soumission["error"] = "{} (segments deja soumis : {})".format(
                soumission.get("error", "echec de soumission"), identifiants
            )
            soumission["job_ids"] = identifiants
            return soumission
        precedent = soumission["job_id"]
        script_path = soumission["script_path"]
        identifiants.append(precedent)

    return {
        "ok": True, "submitted": True, "job_ids": identifiants,
        "resolved": resume, "warnings": plan.warnings,
        "next_step": (
            "Les segments s'enchainent automatiquement. Suis le premier avec "
            "job_status('{}'). Pour tout arreter, annule-les tous : la "
            "dependance seule ne suffit pas.".format(identifiants[0])
        ),
    }

# =============================================================================
# Ordonnancement : part d'usage et creneau
# =============================================================================
@outil(
    annotations=READ_ONLY,
    description=(
        "Estime l'effet d'une charge envisagee sur la part d'usage du compte, "
        "donc sur la priorite des jobs suivants de l'equipe. Lit l'usage "
        "courant via sshare et le compare a la consommation projetee."
    ),
)
def romeo_fairshare_forecast(
    simulated_cpus: int = 0, simulated_gpus: int = 0, duration_hours: float = 1.0
) -> dict[str, Any]:
    """Projette l'usage supplementaire sur la part d'ordonnancement."""
    require_account()
    s = session()
    try:
        resultat = _sh(
            s,
            "sshare -A {} -a -P -o Account,User,RawShares,NormShares,RawUsage,"
            "EffectvUsage,FairShare 2>/dev/null".format(shlex.quote(DEFAULT_ACCOUNT)),
            timeout=45, max_chars=12_000,
        )
    except (SSHError, SSHTimeout) as exc:
        return _error(str(exc))

    lignes = parse_pipe_table(resultat.stdout)
    if not lignes:
        return _error("sshare n'a rien renvoye pour le compte {}.".format(DEFAULT_ACCOUNT))

    compte = next((l for l in lignes if not (l.get("User") or "").strip()), lignes[0])
    moi = next((l for l in lignes if (l.get("User") or "").strip() == s.user), None)

    def _nombre(valeur):
        try:
            return float(valeur)
        except (TypeError, ValueError):
            return None

    usage_brut = _nombre(compte.get("RawUsage")) or 0.0
    usage_effectif = _nombre(compte.get("EffectvUsage")) or 0.0

    # Aucune ponderation TRESBillingWeights n'est definie sur les partitions :
    # SLURM facture donc au coeur. Les GPU ne sont pas comptes a part, mais ils
    # imposent en pratique de reserver des coeurs.
    cpus = max(0, int(simulated_cpus))
    heures = max(0.0, float(duration_hours))
    ajout = cpus * heures * 3600.0

    total_estime = usage_brut / usage_effectif if usage_effectif else None
    nouvel_effectif = (
        (usage_brut + ajout) / total_estime if total_estime else None
    )
    hausse_pct = (ajout / usage_brut * 100) if usage_brut else None

    lecture = []
    if hausse_pct is None:
        lecture.append("usage courant nul : impossible de projeter une hausse relative.")
    elif hausse_pct < 5:
        lecture.append(
            "Hausse de {:.1f} % de l'usage du compte : effet negligeable sur la "
            "priorite de l'equipe.".format(hausse_pct)
        )
    elif hausse_pct < 30:
        lecture.append(
            "Hausse de {:.0f} % de l'usage du compte : la priorite des jobs "
            "suivants baissera de facon perceptible pendant quelques jours, le "
            "temps que l'usage se decroisse.".format(hausse_pct)
        )
    else:
        lecture.append(
            "Hausse de {:.0f} % de l'usage du compte : effet marque sur la "
            "priorite de toute l'equipe. Envisage d'etaler le calcul, ou "
            "previens tes collegues.".format(hausse_pct)
        )
    if simulated_gpus:
        lecture.append(
            "Les {} GPU demandes ne sont pas factures separement : aucune "
            "ponderation TRESBillingWeights n'est definie sur les partitions, "
            "la facturation se fait au coeur.".format(simulated_gpus)
        )
    lecture.append(
        "La formule exacte de priorite n'est pas publique : ces chiffres "
        "situent un ordre de grandeur, ils ne predisent pas un rang de file."
    )

    return {
        "ok": True,
        "compte": DEFAULT_ACCOUNT,
        "usage_brut_actuel": usage_brut,
        "usage_effectif_actuel": usage_effectif,
        "ma_part": {
            "utilisateur": s.user,
            "usage_brut": _nombre(moi.get("RawUsage")) if moi else None,
            "fairshare": _nombre(moi.get("FairShare")) if moi else None,
        },
        "charge_simulee": {
            "coeurs": cpus, "gpus": simulated_gpus, "heures": heures,
            "cout_coeur_secondes": round(ajout),
        },
        "usage_effectif_projete": (
            round(nouvel_effectif, 6) if nouvel_effectif is not None else None
        ),
        "hausse_relative_pct": round(hausse_pct, 1) if hausse_pct is not None else None,
        "lecture": lecture,
    }

@outil(
    annotations=READ_ONLY,
    description=(
        "Recommande ou soumettre en confrontant la file d'attente a l'etat du "
        "parc : quelle partition et quelle architecture demarreraient le plus "
        "vite pour la taille de job envisagee."
    ),
)
def suggest_submission_slot(
    nodes: int = 1, gpus_per_node: int = 0, hours: float = 1.0
) -> dict[str, Any]:
    """Compare les partitions pour la forme de job demandee."""
    s = session()
    etat = romeo_status(include_queue=True)
    if not etat.get("ok"):
        return etat

    try:
        attente = _sh(
            s, "squeue -h -t PENDING -o '%P|%D' 2>/dev/null", timeout=40,
            max_chars=40_000,
        )
    except (SSHError, SSHTimeout) as exc:
        return _error(str(exc))

    file_par_partition: dict[str, int] = {}
    for ligne in attente.stdout.splitlines():
        morceaux = ligne.split("|")
        if morceaux and morceaux[0].strip():
            nom = morceaux[0].strip().rstrip("*")
            file_par_partition[nom] = file_par_partition.get(nom, 0) + 1

    arch = "armgpu" if gpus_per_node > 0 else "x64cpu"
    inventaire = (etat.get("nodes") or {}).get(arch, {})
    libres = inventaire.get("idle", 0)
    partiels = inventaire.get("mixed", 0)

    secondes = max(60, int(float(hours) * 3600))
    options = []
    for nom in PARTITION_ORDER:
        partition = PARTITIONS[nom]
        capacite = partition["nodes_by_arch"].get(arch, 0)
        tient = secondes <= partition["max_seconds"]
        assez = nodes <= capacite
        options.append(
            {
                "partition": nom,
                "convient": bool(tient and assez),
                "limite_temps": format_slurm_time(partition["max_seconds"]),
                "noeuds_exposes": capacite,
                "jobs_en_attente": file_par_partition.get(nom, 0),
                "raison": (
                    "temps demande superieur a la limite" if not tient
                    else "n'expose que {} noeuds {}".format(capacite, arch)
                    if not assez else "compatible"
                ),
            }
        )

    eligibles = [o for o in options if o["convient"]]
    # On vise la partition la plus courte qui convient : elle expose davantage
    # de noeuds, et l'ordonnanceur y place plus facilement un job en
    # remplissage opportuniste. La profondeur de file est indicative : trois
    # jobs de plusieurs jours bloquent plus qu'une dizaine de jobs d'une heure.
    recommandee = min(
        eligibles, key=lambda o: PARTITION_ORDER.index(o["partition"])
    ) if eligibles else None

    conseils = []
    if recommandee:
        conseils.append(
            "Vise `{}` : c'est la partition la plus courte qui couvre {} h, "
            "elle expose {} noeuds {} et l'ordonnanceur y insere plus "
            "facilement un job en remplissage. ({} job(s) en attente.)".format(
                recommandee["partition"], hours, recommandee["noeuds_exposes"],
                arch, recommandee["jobs_en_attente"],
            )
        )
        plus_calme = [
            o for o in eligibles
            if o["jobs_en_attente"] * 3 < recommandee["jobs_en_attente"]
        ]
        if plus_calme:
            conseils.append(
                "`{}` est nettement moins encombree ({} en attente contre {}) : "
                "a considerer si ta demande est volumineuse.".format(
                    plus_calme[0]["partition"], plus_calme[0]["jobs_en_attente"],
                    recommandee["jobs_en_attente"],
                )
            )
    else:
        conseils.append(
            "Aucune partition ne convient a {} noeud(s) {} pendant {} h. Reduis "
            "la taille ou la duree.".format(nodes, arch, hours)
        )
    if libres >= nodes:
        conseils.append(
            "{} noeuds {} sont entierement libres : un job de cette taille peut "
            "demarrer immediatement.".format(libres, arch)
        )
    elif libres + partiels >= nodes:
        conseils.append(
            "Seulement {} noeuds {} entierement libres, mais {} sont "
            "partiellement occupes : un job plus modeste y demarrerait tout de "
            "suite.".format(libres, arch, partiels)
        )
    else:
        conseils.append(
            "Le parc {} est charge ({} libres pour {} demandes) : attends-toi a "
            "patienter en file.".format(arch, libres, nodes)
        )

    return {
        "ok": True, "arch": arch, "nodes_demandes": nodes,
        "noeuds_libres": libres, "noeuds_partiels": partiels,
        "options": options,
        "recommandation": recommandee["partition"] if recommandee else None,
        "conseils": conseils,
    }

# =============================================================================
# Enchainements de jobs
# =============================================================================
@outil(
    annotations=MUTATING,
    description=(
        "Soumet un enchainement de jobs relies par des dependances SLURM : "
        "preparer, calculer, rassembler. Chaque etape decrit une intention "
        "(commande, temps, ressources) et les etapes dont elle depend ; le "
        "serveur ordonne, valide chacune comme submit_job le ferait, et pose "
        "les --dependency. L'architecture declaree pour l'enchainement est "
        "heritee par toutes les etapes, ce qui evite qu'une etape sans GPU "
        "parte sur x86_64 alors que les autres tournent en aarch64. "
        "SIMULATION PAR DEFAUT : rappelle avec confirm=true pour soumettre."
    ),
)
def submit_pipeline(
    name: str,
    stages: list[dict],
    arch: str | None = None,
    spack_packages: list[str] | None = None,
    modules: list[str] | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Valide et soumet un graphe d'etapes dependantes."""
    require_account()
    s = session()
    if not _NOM_ENCHAINEMENT.match(name or ""):
        return _error(
            "nom d'enchainement invalide : {!r}. Attendu 1 a 48 caracteres "
            "parmi lettres, chiffres, point, tiret et souligne.".format(name)
        )

    try:
        etapes = ordonner(valider_etapes(stages))
    except ClusterError as exc:
        return _error(str(exc))

    try:
        foyer, racine, alias, hors_ligne = _contexte_chemins(s, confirm)
    except (SSHError, SSHTimeout) as exc:
        return _error(str(exc))

    defauts = {"arch": arch, "spack_packages": spack_packages, "modules": modules}
    plans, resume, avertissements = [], [], ([hors_ligne] if hors_ligne else [])

    for etape in etapes:
        fusionnee = heriter(etape, defauts)
        spec = JobSpec(
            name="{}-{}".format(name, fusionnee["name"])[:64],
            command=fusionnee["command"],
            time=fusionnee.get("time_limit") or "1h",
            nodes=int(fusionnee.get("nodes") or 1),
            ntasks_per_node=int(fusionnee.get("ntasks_per_node") or 1),
            cpus_per_task=int(fusionnee.get("cpus_per_task") or 1),
            gpus_per_node=int(fusionnee.get("gpus_per_node") or 0),
            mem_gb=fusionnee.get("mem_gb"),
            arch=fusionnee.get("arch"),
            partition=fusionnee.get("partition"),
            modules=fusionnee.get("modules") or [],
            spack_packages=fusionnee.get("spack_packages") or [],
            workdir=posixpath.join(racine, "mcp-pipelines", name, fusionnee["name"]),
            array=fusionnee.get("array"),
            distributed=fusionnee.get("distributed"),
            container=fusionnee.get("container"),
            redirect_caches=bool(fusionnee.get("redirect_caches")),
            job_tmpdir=bool(fusionnee.get("job_tmpdir")),
        )
        try:
            plan = plan_job(spec, racine)
        except (ClusterError, GuardError) as exc:
            return _error(
                "etape {!r} : {}. Rien n'a ete soumis : un enchainement est "
                "valide en entier avant que la premiere etape ne parte.".format(
                    etape["name"], exc)
            )
        plans.append((etape, plan))
        avertissements.extend(
            "etape {} : {}".format(etape["name"], a) for a in plan.warnings
        )
        resume.append({
            "stage": etape["name"],
            "depends_on": etape["depends_on"],
            "condition": etape["condition"],
            "partition": plan.partition,
            "arch": plan.arch,
            "time": format_slurm_time(plan.seconds),
            "total_cpus": plan.total_cpus,
            "total_gpus": plan.total_gpus,
            "workdir": plan.workdir,
        })

    if not confirm:
        return {
            "ok": True,
            "submitted": False,
            "mode": "simulation",
            "pipeline": name,
            "order": [e["name"] for e, _ in plans],
            "stages": resume,
            "warnings": avertissements,
            "scripts": {e["name"]: p.script for e, p in plans},
            "next_step": (
                "Relis l'ordre, les architectures et les avertissements, puis "
                "rappelle submit_pipeline avec confirm=true pour soumettre."
            ),
        }

    identifiants: dict[str, str] = {}
    soumis: list[dict] = []
    for etape, plan in plans:
        options = ()
        clause = clause_dependance(etape, identifiants)
        if clause:
            options = (clause,)
        resultat = _soumettre_sbatch(
            s, plan, "{}-{}".format(name, etape["name"]),
            note="enchainement {}".format(name), options=options,
        )
        if not resultat["ok"]:
            # On ne rattrape pas les etapes deja parties : les annuler
            # detruirait un calcul peut-etre deja en cours. On dit exactement
            # ou l'enchainement s'est arrete, et ce qui tourne encore.
            return _error(
                "etape {!r} refusee : {}. Les etapes precedentes sont DEJA "
                "soumises ({}) et vont s'executer. Annule-les avec cancel_job "
                "si l'enchainement incomplet n'a pas de sens.".format(
                    etape["name"], resultat.get("error", ""),
                    ", ".join("{}={}".format(k, v) for k, v in identifiants.items())
                    or "aucune"),
                submitted_stages=soumis,
            )
        identifiants[etape["name"]] = resultat["job_id"]
        soumis.append({
            "stage": etape["name"],
            "job_id": resultat["job_id"],
            "depends_on": [identifiants[d] for d in etape["depends_on"]],
        })

    return {
        "ok": True,
        "submitted": True,
        "pipeline": name,
        "stages": soumis,
        "job_ids": list(identifiants.values()),
        "warnings": avertissements,
        "next_step": (
            "Suis l'enchainement avec list_jobs. Une etape en etat "
            "DependencyNeverSatisfied signale qu'une etape amont a echoue : "
            "diagnose_job sur celle-ci."
        ),
    }
