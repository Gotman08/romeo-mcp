"""Construction, validation et lecture des jobs SLURM.

Le point cle : le modele ne redige jamais d'en-tete sbatch. Il decrit une
intention (temps, coeurs, GPU, commande) et ce module produit un script
correct pour ROMEO, ou refuse avec un message qui explique quoi corriger.
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, field

from .templates import (
    FAMILLES_DISTRIBUEES,
    enveloppe_resiliente,
    preambule_staging_shm,
    attend_une_tache_par_noeud,
    enveloppe_conteneur,
    FAMILLES_PYTORCH,
    exports_caches,
    options_affinite,
    preambule_nettoyage,
    preambule_tmpdir,
    lanceur_distribue,
    preambule_distribue,
)
from .cluster import (
    ARCHS,
    DEFAULT_ACCOUNT,
    DEFAULT_QOS,
    PARTITION_ORDER,
    PARTITIONS,
    USER_MAX_CPUS,
    USER_MAX_GPUS,
    ClusterError,
    format_slurm_time,
    parse_duration,
    pick_partition,
    resolve_arch,
    require_account,
)

_NAME_OK = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_ARRAY_OK = re.compile(r"^[0-9]+(-[0-9]+)?(:[0-9]+)?(,[0-9]+(-[0-9]+)?)*(%[0-9]+)?$")


@dataclass
class JobSpec:
    """Intention de calcul, exprimee en termes metier et non en flags sbatch."""

    name: str
    command: str
    time: str = "1h"
    nodes: int = 1
    ntasks_per_node: int = 1
    cpus_per_task: int = 1
    gpus_per_node: int = 0
    mem_gb: int | None = None
    arch: str | None = None
    partition: str | None = None
    modules: list[str] = field(default_factory=list)
    #: Paquets Spack, charges apres la fonction d'environnement de
    #: l'architecture cible (voie officielle ROMEO pour les logiciels).
    spack_packages: list[str] = field(default_factory=list)
    workdir: str | None = None
    array: str | None = None
    account: str = DEFAULT_ACCOUNT
    qos: str = DEFAULT_QOS
    #: Famille de lancement multi-GPU : ddp, accelerate, deepspeed ou srun.
    distributed: str | None = None
    #: Image Apptainer dans laquelle executer la commande.
    container: str | None = None
    container_binds: list[str] = field(default_factory=list)
    #: Detourne les caches des bibliotheques Python hors du home. Sans objet
    #: pour un code compile, d'ou une activation explicite.
    redirect_caches: bool = False
    nccl_debug: bool = False
    #: Archive deballee en memoire vive au demarrage du job.
    stage_archive: str | None = None
    #: Rend le job interruptible et reprenable depuis ce repertoire.
    checkpoint_dir: str | None = None
    #: Preavis SIGUSR1 avant expiration du temps alloue, en secondes.
    signal_before: int = 0
    #: Repertoire temporaire propre au job, detruit a la sortie.
    job_tmpdir: bool = False
    #: Motifs rapatries avant destruction du repertoire temporaire.
    keep_patterns: list[str] = field(default_factory=list)
    #: Mode de liaison CPU passe a srun (cores, threads, sockets...).
    cpu_bind: str | None = None
    #: Fichier distant de variables sensibles, source au demarrage.
    secret_env_file: str | None = None
    #: Fichiers explicites empreintes sur le noeud juste avant le calcul.
    data_files: list[str] = field(default_factory=list)


@dataclass
class Plan:
    """Job valide et pret a soumettre."""

    spec: JobSpec
    seconds: int
    partition: str
    arch: str
    workdir: str
    script: str
    warnings: list[str]

    @property
    def total_cpus(self) -> int:
        return (
            self.spec.nodes * self.spec.ntasks_per_node * self.spec.cpus_per_task
        )

    @property
    def total_gpus(self) -> int:
        return self.spec.nodes * self.spec.gpus_per_node


def plan_job(spec: JobSpec, scratch: str) -> Plan:
    """Valide une intention et rend le script sbatch correspondant.

    Leve :class:`ClusterError` avec un message actionnable des qu'une contrainte
    de ROMEO est violee : cela evite un aller-retour de soumission refusee.
    """
    warnings: list[str] = []

    require_account(spec.account)

    if not _NAME_OK.match(spec.name or ""):
        raise ClusterError(
            "nom de job invalide : {!r}. Attendu 1 a 64 caracteres parmi "
            "lettres, chiffres, point, tiret et souligne.".format(spec.name)
        )
    if not (spec.command or "").strip():
        raise ClusterError("commande vide : il n'y a rien a executer.")
    from .privacy import sensitive_path
    if len(spec.data_files) > 20 or any(
        not p.startswith("/") or "\n" in p or "\x00" in p or sensitive_path(p)
        for p in spec.data_files
    ):
        raise ClusterError("data_files attend au plus 20 chemins absolus de donnees, sans fichier sensible.")

    seconds = parse_duration(spec.time)
    if seconds < 60:
        raise ClusterError("temps demande trop court : minimum 1 minute.")

    arch = resolve_arch(spec.arch, spec.gpus_per_node)
    # Une architecture *deduite* n'est pas une architecture *demandee*. Sur un
    # cluster heterogene, une etape sans GPU d'un enchainement dont les autres
    # etapes sont en aarch64 part silencieusement en x86_64 : l'environnement
    # Python et les binaires construits par les etapes precedentes y sont
    # inutilisables. Le serveur ne peut pas deviner l'intention, mais il peut
    # cesser de decider sans le dire -- comme il le fait deja pour la memoire.
    if not spec.arch and arch == "x64cpu":
        warnings.append(
            "architecture deduite : x64cpu, parce qu'aucun GPU n'est demande. "
            "Si ce calcul lit un environnement ou des binaires produits sur "
            "armgpu (aarch64), precise arch='armgpu' : sinon il echouera sur "
            "un `Illegal instruction` ou un module Python introuvable."
        )
    node = ARCHS[arch]

    if spec.partition:
        if spec.partition not in PARTITIONS:
            raise ClusterError(
                "partition inconnue : {!r}. Valeurs : {}.".format(
                    spec.partition, ", ".join(PARTITIONS)
                )
            )
        limit = PARTITIONS[spec.partition]["max_seconds"]
        if seconds > limit:
            raise ClusterError(
                "--time={} depasse la limite de la partition {} ({}). Utilise "
                "la partition {} ou reduis le temps demande.".format(
                    format_slurm_time(seconds),
                    spec.partition,
                    format_slurm_time(limit),
                    pick_partition(seconds),
                )
            )
        partition = spec.partition
    else:
        partition = pick_partition(seconds)

    if spec.nodes < 1:
        raise ClusterError("nodes doit valoir au moins 1.")
    if spec.nodes > node["node_count"]:
        raise ClusterError(
            "{} noeuds demandes mais la famille {} n'en compte que {} ({}).".format(
                spec.nodes, arch, node["node_count"], node["nodes"]
            )
        )
    # Chaque partition n'expose qu'un sous-ensemble du parc : sans ce controle,
    # le job serait accepte puis resterait indefiniment en attente.
    available = PARTITIONS[partition]["nodes_by_arch"].get(arch, 0)
    if spec.nodes > available:
        hint = next(
            (
                name
                for name in PARTITION_ORDER
                if PARTITIONS[name]["nodes_by_arch"].get(arch, 0) >= spec.nodes
            ),
            None,
        )
        suggestion = (
            " La partition `{}` en offre assez, mais elle plafonne a {}.".format(
                hint, format_slurm_time(PARTITIONS[hint]["max_seconds"])
            )
            if hint
            else ""
        )
        raise ClusterError(
            "{} noeuds {} demandes, mais la partition `{}` (deduite de ton temps "
            "de {}) n'en expose que {}. Le job resterait en attente "
            "indefiniment.{}".format(
                spec.nodes,
                arch,
                partition,
                format_slurm_time(seconds),
                available,
                suggestion,
            )
        )
    if spec.ntasks_per_node < 1 or spec.cpus_per_task < 1:
        raise ClusterError("ntasks_per_node et cpus_per_task doivent valoir >= 1.")

    # --- topologie du lancement distribue ----------------------------------
    # Ajustee avant tout calcul de coeurs et de memoire, qui en decoulent.
    if spec.distributed:
        spec.distributed = spec.distributed.strip().lower()
        if spec.distributed not in FAMILLES_DISTRIBUEES:
            raise ClusterError(
                "famille de lancement inconnue : {!r}. Valeurs : {}.".format(
                    spec.distributed, ", ".join(FAMILLES_DISTRIBUEES)
                )
            )
        # Seules les familles PyTorch supposent des GPU ; le MPI generique
        # sert aussi bien un calcul purement scalaire.
        if spec.distributed in FAMILLES_PYTORCH and spec.gpus_per_node < 1:
            raise ClusterError(
                "distributed={} suppose au moins un GPU par noeud. Pour un "
                "calcul parallele sans GPU, utilise distributed='mpi'."
                .format(spec.distributed)
            )
        # Chaque famille attend une topologie de taches precise. La corriger
        # ici evite un echec NCCL tardif, difficile a relier a sa cause.
        # MPI laisse l'utilisateur maitre de sa topologie de taches.
        if spec.distributed == "mpi":
            pass
        elif attend_une_tache_par_noeud(spec.distributed):
            if spec.ntasks_per_node != 1:
                warnings.append(
                    "{} deploie lui-meme un processus par GPU : ntasks_per_node "
                    "ramene de {} a 1 pour ne pas dupliquer les rangs.".format(
                        spec.distributed, spec.ntasks_per_node
                    )
                )
                spec.ntasks_per_node = 1
        elif spec.ntasks_per_node != spec.gpus_per_node:
            warnings.append(
                "{} attend un processus SLURM par GPU : ntasks_per_node porte "
                "de {} a {}.".format(
                    spec.distributed, spec.ntasks_per_node, spec.gpus_per_node
                )
            )
            spec.ntasks_per_node = spec.gpus_per_node

    cpus_per_node = spec.ntasks_per_node * spec.cpus_per_task
    if cpus_per_node > node["cpus_per_node"]:
        raise ClusterError(
            "{} coeurs par noeud demandes ({} taches x {} coeurs) mais un noeud "
            "{} en offre {}.".format(
                cpus_per_node,
                spec.ntasks_per_node,
                spec.cpus_per_task,
                arch,
                node["cpus_per_node"],
            )
        )

    if spec.gpus_per_node > node["gpus_per_node"]:
        raise ClusterError(
            "{} GPU par noeud demandes mais un noeud {} en compte {}.".format(
                spec.gpus_per_node, arch, node["gpus_per_node"]
            )
        )

    # ROMEO refuse toute soumission sans --mem ("Memory resource is missing").
    # Plutot que de renvoyer l'erreur au modele, on derive une part de memoire
    # proportionnelle aux coeurs demandes : toujours valide, jamais superieure
    # a la capacite du noeud.
    available_gb = node["mem_mb_per_node"] // 1024
    if spec.mem_gb is None:
        share = available_gb * cpus_per_node // node["cpus_per_node"]
        spec.mem_gb = max(1, share)
        warnings.append(
            "aucune memoire demandee : ROMEO l'exige, donc {} Go ont ete "
            "derives de tes {} coeurs (part proportionnelle du noeud). Precise "
            "mem_gb si le calcul a un profil memoire different.".format(
                spec.mem_gb, cpus_per_node
            )
        )
    else:
        if spec.mem_gb < 1:
            raise ClusterError("mem_gb doit valoir au moins 1.")
        if spec.mem_gb > available_gb:
            raise ClusterError(
                "{} Go par noeud demandes mais un noeud {} en offre {} Go.".format(
                    spec.mem_gb, arch, available_gb
                )
            )

    if spec.array is not None and not _ARRAY_OK.match(spec.array):
        raise ClusterError(
            "syntaxe de tableau invalide : {!r}. Exemples : '0-9', '1,3,5', "
            "'0-99%10'.".format(spec.array)
        )

    if spec.container:
        if arch == "armgpu":
            warnings.append(
                "conteneur sur noeud aarch64 : l'image doit etre construite "
                "pour arm64. Une image NGC x86 se lance mais echoue au premier "
                "appel de noyau."
            )
        if not spec.container_binds:
            # Sans montage explicite, le job ecrirait dans le systeme de
            # fichiers ephemere de l'image et perdrait ses resultats.
            spec.container_binds = [scratch, "/project"]

    # --- avertissements : ne bloquent pas, mais orientent le modele ---------
    if spec.gpus_per_node and spec.cpus_per_task == 1 and spec.ntasks_per_node == 1:
        warnings.append(
            "1 seul coeur pour {} GPU : le chargement des donnees sera le "
            "goulot. Compte 16 a 32 coeurs par GPU.".format(spec.gpus_per_node)
        )
    if arch == "armgpu":
        warnings.append(
            "cible aarch64 : tout binaire ou paquet Python compile depuis le "
            "noeud de login (x86_64) echouera. Utilise compute_command_prepare."
        )
    if partition == "instant" and seconds > 1800:
        warnings.append(
            "la partition instant coupe a 1 h : prevois un checkpoint si le "
            "calcul peut deborder."
        )

    # Plafonds du compte : relevables sur ticket, donc avertissement et non refus.
    total_cpus = spec.nodes * cpus_per_node
    total_gpus = spec.nodes * spec.gpus_per_node
    if USER_MAX_CPUS > 0 and total_cpus > USER_MAX_CPUS:
        warnings.append(
            "{} coeurs demandes alors que ton compte est plafonne a {} : le job "
            "restera en attente. Verifie avec `sacctmgr show assoc where "
            "user=$USER`.".format(total_cpus, USER_MAX_CPUS)
        )
    if USER_MAX_GPUS > 0 and total_gpus > USER_MAX_GPUS:
        warnings.append(
            "{} GPU demandes alors que ton compte est plafonne a {} : le job "
            "restera en attente.".format(total_gpus, USER_MAX_GPUS)
        )

    # Parallelisme hybride : plusieurs rangs par noeud sans fil OpenMP
    # laisse le gros des coeurs inutilises sur des noeuds a 192 ou 288 coeurs.
    if spec.ntasks_per_node > 1 and spec.cpus_per_task == 1:
        libres = node["cpus_per_node"] - cpus_per_node
        if libres > node["cpus_per_node"] // 2:
            warnings.append(
                "{} taches d'un seul coeur sur un noeud qui en compte {} : "
                "{} coeurs resteront inutilises. Si ton code est compile avec "
                "OpenMP, augmente cpus_per_task ; OMP_NUM_THREADS en decoule "
                "automatiquement.".format(
                    spec.ntasks_per_node, node["cpus_per_node"], libres)
            )

    # OpenMPI a besoin de srun pour dialoguer avec SLURM : sans lui, les rangs
    # ne communiquent pas et le calcul est faux ou bloque. Inutile de le
    # rappeler quand un lanceur distribue est demande : il ajoute deja srun.
    if not spec.distributed and (spec.nodes > 1 or spec.ntasks_per_node > 1) and not re.search(
        r"\b(srun|mpirun|mpiexec)\b", spec.command
    ):
        warnings.append(
            "job multi-taches ({} noeuds x {} taches) dont la commande n'appelle "
            "ni srun ni mpirun : SLURM lancera la meme commande en parallele sans "
            "coordination. Prefixe par `srun` pour un calcul MPI.".format(
                spec.nodes, spec.ntasks_per_node
            )
        )

    workdir = spec.workdir or posixpath.join(scratch, "mcp-jobs", spec.name)
    script = render_sbatch(spec, seconds, partition, arch, workdir, scratch)
    return Plan(
        spec=spec,
        seconds=seconds,
        partition=partition,
        arch=arch,
        workdir=workdir,
        script=script,
        warnings=warnings,
    )


def render_sbatch(
    spec: JobSpec, seconds: int, partition: str, arch: str, workdir: str,
    scratch: str = "",
) -> str:
    """Produit le script sbatch complet."""
    node = ARCHS[arch]
    pattern = "%x-%A_%a" if spec.array is not None else "%x-%j"

    directives = [
        ("job-name", spec.name),
        ("account", spec.account),
        ("qos", spec.qos),
        ("partition", partition),
        ("constraint", node["feature"]),
        ("time", format_slurm_time(seconds)),
        ("nodes", str(spec.nodes)),
        ("ntasks-per-node", str(spec.ntasks_per_node)),
        ("cpus-per-task", str(spec.cpus_per_task)),
    ]
    if spec.gpus_per_node:
        # Forme documentee par ROMEO. `--gres=gpu:h100:N` fonctionne aussi
        # (verifie par soumission reelle) mais n'apparait nulle part dans la
        # documentation officielle.
        directives.append(("gpus-per-node", str(spec.gpus_per_node)))
    if spec.mem_gb is not None:
        directives.append(("mem", "{}G".format(spec.mem_gb)))
    if spec.array is not None:
        directives.append(("array", spec.array))
    if spec.signal_before:
        # `B:` vise le script de traitement par lots lui-meme, et non les
        # etapes lancees par srun.
        directives.append(("signal", "B:SIGUSR1@{}".format(spec.signal_before)))
    directives += [
        ("chdir", workdir),
        ("output", "{}/{}.out".format(workdir, pattern)),
        ("error", "{}/{}.err".format(workdir, pattern)),
    ]

    # Shebang de la documentation officielle. Un `#!/bin/bash -l` fonctionne
    # aussi : SLURM exporte les fonctions shell du shell soumetteur, donc
    # `romeo_load_*_env` reste definie dans les deux cas (verifie par
    # soumission comparee).
    lines = ["#!/usr/bin/env bash", "# Genere par romeo-mcp - ne pas editer a la main."]
    lines += ["#SBATCH --{}={}".format(key, value) for key, value in directives]
    lines += ["", "set -euo pipefail", ""]

    # Environment Modules est l'outillage de l'ancien calculateur : on ne l'active
    # que sur demande explicite.
    if spec.modules:
        lines.append("module purge")
        lines += ["module load {}".format(m) for m in spec.modules]
        lines.append("")

    lines += [
        "# Sans cette fonction, un job ROMEO 2025 n'a acces a aucun logiciel,",
        "# pas meme a la commande spack. Elle est propre a l'architecture :",
        "# charger celle de l'autre donnerait des binaires inutilisables.",
        node["env_loader"],
    ]
    lines += ["spack load {}".format(p) for p in spec.spack_packages]

    if spec.secret_env_file:
        lines += [
            "",
            "# Variables sensibles lues depuis un fichier a droits restreints :",
            "# elles n'apparaissent ni dans ce script, ni dans le registre local.",
            'if [ -r "{f}" ]; then set -a; . "{f}"; set +a; else'.format(
                f=spec.secret_env_file
            ),
            '  echo "[romeo-mcp] fichier de secrets illisible : {}" >&2; exit 1'.format(
                spec.secret_env_file
            ),
            "fi",
        ]

    if spec.redirect_caches and scratch:
        lines += [""] + exports_caches(scratch)

    # Une seule file de nettoyage, partagee par le repertoire temporaire et la
    # mise en cache memoire : deux pieges EXIT s'ecraseraient.
    if spec.job_tmpdir or spec.stage_archive:
        lines += [""] + preambule_nettoyage()

    if spec.job_tmpdir and scratch:
        lines += [""] + preambule_tmpdir(scratch, spec.keep_patterns or None)

    if spec.distributed:
        lines += [""] + preambule_distribue(
            spec.distributed, spec.gpus_per_node, spec.nccl_debug
        )

    if spec.stage_archive:
        lines += [""] + preambule_staging_shm(spec.stage_archive)

    from .reproducibility import runtime_fragment
    lines += runtime_fragment(workdir, scratch, spec.data_files)

    commande = spec.command.strip()
    if spec.container:
        commande = enveloppe_conteneur(spec.container, commande, spec.container_binds)
    if spec.distributed:
        commande = lanceur_distribue(
            spec.distributed, commande, spec.gpus_per_node,
            options_affinite(spec.cpus_per_task, spec.cpu_bind),
        )

    lines += [
        "",
        '# Trace d\'execution : sert a diagnostiquer les erreurs d\'architecture.',
        'echo "[romeo-mcp] noeud=$(hostname) arch=$(uname -m) job=${SLURM_JOB_ID:-?}"',
        'echo "[romeo-mcp] debut $(date -Is)"',
        "",
    ]
    if spec.checkpoint_dir:
        lines += enveloppe_resiliente(
            commande, spec.checkpoint_dir, spec.signal_before or 300
        )
        # L'enveloppe resiliente se termine par son propre `exit` : toute
        # ligne ajoutee apres serait inatteignable.
    else:
        lines.append(commande)
        lines += ["", 'echo "[romeo-mcp] fin $(date -Is)"']
    lines.append("")
    return "\n".join(lines)


# --- lecture de l'etat des jobs --------------------------------------------
_SACCT_DURATION = re.compile(
    r"^(?:(\d+)-)?(?:(\d+):)?(\d+):(\d+(?:\.\d+)?)$"
)
_MEM = re.compile(r"^([0-9.]+)\s*([KMGTP]?)", re.IGNORECASE)
_MEM_SCALE = {"": 1 / 1024**2, "K": 1 / 1024, "M": 1.0, "G": 1024.0,
              "T": 1024.0**2, "P": 1024.0**3}

#: Etats SLURM consideres comme termines.
TERMINAL_STATES = {
    "COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "OUT_OF_MEMORY",
    "NODE_FAIL", "PREEMPTED", "BOOT_FAIL", "DEADLINE", "REVOKED",
}


def parse_sacct_duration(text: str) -> float | None:
    """Convertit une duree sacct en secondes.

    Gere ``MM:SS.mmm``, ``HH:MM:SS`` et ``D-HH:MM:SS``.
    """
    text = (text or "").strip()
    if not text or text in ("INVALID", "UNLIMITED", "Unknown"):
        return None
    match = _SACCT_DURATION.match(text)
    if not match:
        return None
    days, hours, minutes, seconds = match.groups()
    return (
        int(days or 0) * 86_400
        + int(hours or 0) * 3_600
        + int(minutes) * 60
        + float(seconds)
    )


def parse_mem_mb(text: str) -> float | None:
    """Convertit une taille memoire sacct (``4096K``, ``12.5G``) en Mo."""
    text = (text or "").strip()
    if not text or text in ("0", "Unknown"):
        return None
    match = _MEM.match(text)
    if not match:
        return None
    value, unit = match.groups()
    return float(value) * _MEM_SCALE[unit.upper()]


def parse_pipe_table(output: str) -> list[dict[str, str]]:
    """Lit une sortie SLURM au format ``--parsable2`` (separateur ``|``)."""
    rows: list[dict[str, str]] = []
    lines = [line for line in output.splitlines() if line.strip()]
    if not lines:
        return rows
    header = lines[0].split("|")
    for line in lines[1:]:
        cells = line.split("|")
        if len(cells) < len(header):
            cells += [""] * (len(header) - len(cells))
        rows.append(dict(zip(header, cells)))
    return rows


def gpus_from_tres(tres: str) -> int:
    """Extrait le nombre de GPU d'une chaine AllocTRES."""
    match = re.search(r"gres/gpu(?::[a-z0-9]+)?=(\d+)", tres or "")
    return int(match.group(1)) if match else 0


def summarize_efficiency(rows: list[dict[str, str]], job_id: str) -> dict:
    """Recalcule les metriques de ``seff``, absent de ROMEO.

    ``sacct`` ventile un job en une ligne principale et des lignes d'etape
    (``.batch``, ``.0``...). Le temps CPU et la RSS maximale ne sont fiables que
    sur les etapes, d'ou l'agregation.
    """
    main = next((r for r in rows if r.get("JobID") == job_id), None)
    if main is None:
        return {"found": False, "job_id": job_id}

    steps = [r for r in rows if r.get("JobID", "").startswith(job_id + ".")]
    elapsed = parse_sacct_duration(main.get("Elapsed", "")) or 0.0
    alloc_cpus = int(main.get("AllocCPUS") or 0)

    cpu_seconds = parse_sacct_duration(main.get("TotalCPU", ""))
    if not cpu_seconds:
        cpu_seconds = sum(
            parse_sacct_duration(s.get("TotalCPU", "")) or 0.0 for s in steps
        )

    # Absence de mesure et mesure nulle sont deux choses differentes : sacct ne
    # rapporte pas de MaxRSS pour un job annule tot ou dont la comptabilite
    # d'etape est desactivee. Les confondre faisait annoncer « 0 % de memoire
    # utilisee » et conseiller de reduire la reservation d'un job qui en avait
    # besoin ; le run suivant mourait en OUT_OF_MEMORY.
    releves = [
        valeur
        for valeur in (parse_mem_mb(etape.get("MaxRSS", "")) for etape in steps)
        if valeur is not None
    ]
    max_rss_mb = max(releves) if releves else None
    req_mem_mb = parse_mem_mb(main.get("ReqMem", ""))

    reserved = elapsed * alloc_cpus
    cpu_eff = (cpu_seconds / reserved * 100) if reserved > 0 else None
    mem_eff = (
        (max_rss_mb / req_mem_mb * 100)
        if (req_mem_mb and max_rss_mb is not None)
        else None
    )

    result = {
        "found": True,
        "job_id": job_id,
        "name": main.get("JobName", ""),
        "state": main.get("State", ""),
        "exit_code": main.get("ExitCode", ""),
        "partition": main.get("Partition", ""),
        "elapsed": main.get("Elapsed", ""),
        "elapsed_seconds": round(elapsed, 1),
        "alloc_cpus": alloc_cpus,
        "alloc_gpus": gpus_from_tres(main.get("AllocTRES", "")),
        "cpu_seconds_used": round(cpu_seconds, 1),
        "cpu_seconds_reserved": round(reserved, 1),
        "cpu_efficiency_pct": round(cpu_eff, 1) if cpu_eff is not None else None,
        "max_rss_mb": round(max_rss_mb, 1) if max_rss_mb is not None else None,
        "req_mem_mb": round(req_mem_mb, 1) if req_mem_mb else None,
        "mem_efficiency_pct": round(mem_eff, 1) if mem_eff is not None else None,
    }
    result["advice"] = _efficiency_advice(result)
    return result


def _efficiency_advice(m: dict) -> list[str]:
    """Traduit les metriques en corrections concretes pour le run suivant."""
    advice: list[str] = []
    cpu = m.get("cpu_efficiency_pct")
    mem = m.get("mem_efficiency_pct")
    cpus = m.get("alloc_cpus") or 0

    if cpu is not None and cpus > 1:
        if cpu < 25:
            useful = max(1, round(cpus * cpu / 100))
            advice.append(
                "efficacite CPU de {:.0f} % sur {} coeurs : le calcul n'en "
                "exploite que ~{}. Reduis cpus_per_task, ou verifie que le code "
                "est reellement parallele (OMP_NUM_THREADS, -j).".format(
                    cpu, cpus, useful
                )
            )
        elif cpu > 95:
            advice.append(
                "efficacite CPU de {:.0f} % : les coeurs sont satures, tu peux "
                "sans doute en demander davantage.".format(cpu)
            )

    if mem is not None:
        # Une marge de securite sur la memoire est saine ; on n'alerte que si
        # la sur-reservation est a la fois large en proportion et en volume,
        # car elle retarde alors l'ordonnancement pour rien.
        wasted_mb = (m.get("req_mem_mb") or 0) - (m.get("max_rss_mb") or 0)
        if mem < 40 and wasted_mb > 16_384:
            advice.append(
                "memoire utilisee a {:.0f} % de la reservation ({:.0f} Mo sur "
                "{:.0f}, soit {:.0f} Go reserves pour rien) : baisse mem_gb, le "
                "job partira plus vite.".format(
                    mem, m.get("max_rss_mb") or 0, m["req_mem_mb"], wasted_mb / 1024
                )
            )
        elif mem > 90:
            advice.append(
                "memoire a {:.0f} % de la reservation : augmente mem_gb pour "
                "eviter un OUT_OF_MEMORY.".format(mem)
            )

    if str(m.get("state", "")).startswith("OUT_OF_MEMORY"):
        advice.append("job tue par manque de memoire : augmente mem_gb.")
    if str(m.get("state", "")).startswith("TIMEOUT"):
        advice.append("job coupe par la limite de temps : augmente time.")
    if not advice:
        advice.append("dimensionnement correct, rien a corriger.")
    return advice
