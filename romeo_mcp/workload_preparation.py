"""Preparation metier des telechargements, chaines reprenables et profilages."""
from __future__ import annotations
from dataclasses import asdict
import posixpath
import shlex
from typing import Any
from urllib.parse import urlparse
from .cluster import ClusterError, require_account, parse_duration, format_slurm_time
from .guard import GuardError, check_path
from .slurm import JobSpec, plan_job
from .ssh import SSHError, SSHTimeout, session
from .plans import prepare_submission, prepare_submission as _prepare_submission
from .execution_backend import _error, _duree_job, _contexte_chemins

def dataset_prepare(
    source: str,
    destination: str,
    kind: str = "auto",
    minutes: int = 60,
    time_limit: str | None = None,
    arch: str = "x64cpu",
    env_path: str | None = None,
) -> dict[str, Any]:
    """Rapatrie des donnees via un job, pour epargner le noeud de login."""
    require_account()
    s = session()
    home, scratch, aliases, offline = _contexte_chemins(s, False)
    if not source.strip():
        return _error("source vide")
    try:
        cible = check_path(destination, home, scratch, aliases)
    except GuardError as exc:
        return _error(str(exc))

    nature = kind.strip().lower()
    if nature == "auto":
        if source.endswith(".git") or "github.com" in source or "romeogit" in source:
            nature = "git"
        elif source.startswith(("http://", "https://")):
            nature = "url"
        else:
            nature = "huggingface"

    if nature == "url":
        commande = "curl -fL --retry 3 -o {} -- {}".format(
            shlex.quote(posixpath.join(cible, posixpath.basename(urlparse(source).path) or "download")),
            shlex.quote(source),
        )
        paquets = ["curl"]
    elif nature == "git":
        commande = "git clone --depth 1 -- {} {}".format(
            shlex.quote(source), shlex.quote(cible)
        )
        paquets = []
    elif nature == "huggingface":
        if not env_path:
            return _error("Hugging Face requiert env_path, un venv existant contenant huggingface_hub. "
                          "Installe ce paquet explicitement avec python_packages_install sur la meme architecture.")
        try:
            environnement = check_path(env_path, home, scratch, aliases)
        except GuardError as exc:
            return _error(str(exc))
        python = shlex.quote(posixpath.join(environnement, "bin", "python"))
        # L'API Python publique evite de dependre du chemin interne de la CLI.
        # Le job de telechargement ne lance jamais d'installateur.
        code = ("import sys; from huggingface_hub import snapshot_download; "
                "snapshot_download(repo_id=sys.argv[1], local_dir=sys.argv[2], repo_type='dataset')")
        commande = (
            "{python} -c 'import huggingface_hub' || {{ "
            "echo 'huggingface_hub absent : utilise python_packages_install dans ce venv.' >&2; exit 1; }}; "
            "{python} -c {code} {source} {destination}"
        ).format(python=python, code=shlex.quote(code), source=shlex.quote(source),
                 destination=shlex.quote(cible))
        paquets = []
    else:
        return _error(
            "type inconnu : {!r}. Valeurs : auto, url, git, huggingface.".format(kind)
        )

    spec = JobSpec(
        name="mcp-staging",
        command="mkdir -p {} && {}".format(shlex.quote(cible), commande),
        time=_duree_job(minutes, time_limit, 24 * 60),
        cpus_per_task=4,
        arch=arch,
        spack_packages=paquets,
        workdir=posixpath.dirname(cible),
    )
    try:
        spec.workdir = posixpath.dirname(cible)
        plan = plan_job(spec, scratch)
    except (ClusterError, SSHError, SSHTimeout) as exc:
        return _error(str(exc))

    return prepare_submission("dataset", s, home, scratch, offline, [{"plan": asdict(plan)}],
                              {"kind": nature, "destination": cible, "script": plan.script,
                               "warnings": plan.warnings, "resolved": {"arch": plan.arch, "destination": cible}})


def job_resilient_prepare(
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
) -> dict[str, Any]:
    """Chaine plusieurs segments dependants autour d'un point de reprise."""
    require_account()
    s = session()
    home, scratch, aliases, offline = _contexte_chemins(s, False)
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

    dossier = checkpoint_dir or posixpath.join(scratch, "ckpts", name)
    try:
        dossier = check_path(dossier, home, scratch, aliases)
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
            spec.workdir = check_path(workdir, home, scratch, aliases)
        plan = plan_job(spec, scratch)
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

    entries = [{"plan": asdict(plan), "reuse_previous_script": bool(i), "stage": {
        "name": str(i), "depends_on": [str(i-1)] if i else [], "condition": "afterany"}}
        for i in range(segments)]
    return _prepare_submission("resilient", s, home, scratch, offline, entries,
                               {"resolved": resume, "warnings": plan.warnings, "script": plan.script,
                                "prerequis": "Le programme doit reprendre le checkpoint et traiter SIGUSR1."})


def job_profile_prepare(
    command: str,
    name: str = "mcp-profile",
    delay_seconds: int = 60,
    duration_seconds: int = 30,
    warmup_steps: int = 5,
    profile_steps: int = 10,
    time_limit: str = "30m",
    gpus_per_node: int = 1,
    cpus_per_task: int = 16,
    arch: str = "armgpu",
    spack_packages: list[str] | None = None,
    workdir: str | None = None,
) -> dict[str, Any]:
    """Soumet un job encapsule dans `nsys profile`, capture fenetree."""
    require_account()
    s = session()
    home, scratch, aliases, offline = _contexte_chemins(s, False)
    if not command.strip():
        return _error("commande vide : il n'y a rien a profiler.")

    delay_seconds = max(0, min(int(delay_seconds), 3600))
    duration_seconds = max(5, min(int(duration_seconds), 600))
    profils = posixpath.join(scratch, "profiles")
    rapport = "{}/{}_$SLURM_JOB_ID".format(profils, name)

    corps = [
        "mkdir -p {}".format(shlex.quote(profils)),
        "# Ces compteurs sont transmis au programme : une capture par etapes",
        "# suppose que le code delimite ses iterations par des marqueurs NVTX.",
        "export PROFILE_WARMUP_STEPS={}".format(int(warmup_steps)),
        "export PROFILE_STEPS={}".format(int(profile_steps)),
        "",
        "# La fenetre de capture evite une trace de plusieurs gigaoctets : on",
        "# laisse le calcul se stabiliser, puis on enregistre quelques dizaines",
        "# de secondes representatives.",
        "nsys profile \\",
        "  --trace=cuda,nvtx,osrt \\",
        "  --delay={} \\".format(delay_seconds),
        "  --duration={} \\".format(duration_seconds),
        "  --force-overwrite true \\",
        '  -o "{}" \\'.format(rapport),
        "  {}".format(command.strip()),
        "",
        'echo "###PROFIL_STATS"',
        'nsys stats --report gpukernsum,gpumemtimesum "{}.nsys-rep" '
        "2>&1 || true".format(rapport),
    ]

    spec = JobSpec(
        name=name,
        command="\n".join(corps),
        time=time_limit,
        gpus_per_node=gpus_per_node,
        cpus_per_task=cpus_per_task,
        arch=arch,
        spack_packages=(spack_packages or []) + ["nvidia-nsight-systems"],
        workdir=workdir,
    )
    try:
        if workdir:
            spec.workdir = check_path(workdir, home, scratch, aliases)
        plan = plan_job(spec, scratch)
    except (ClusterError, GuardError, SSHError, SSHTimeout) as exc:
        return _error(str(exc))

    resume = {
        "profileur": "nsys",
        "fenetre": "{} s apres {} s de mise en regime".format(
            duration_seconds, delay_seconds
        ),
        "rapport": rapport + ".nsys-rep",
        "arch": plan.arch,
        "partition": plan.partition,
    }

    return prepare_submission("profile", s, home, scratch, offline, [{"plan": asdict(plan)}],
                              {"resolved": resume, "warnings": plan.warnings, "script": plan.script,
                               "note": "Les compteurs par etapes exigent des marqueurs NVTX dans le programme."})
