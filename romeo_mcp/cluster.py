"""Faits statiques sur ROMEO (URCA) + helpers de dimensionnement.

Ces constantes sont la source de verite exposee au modele via la ressource
``romeo://cheatsheet``. Elles evitent qu'il invente un nom de partition, un
compte SLURM ou une capacite noeud.

Releve effectue le 2026-08-20 sur romeo1.univ-reims.fr.
"""

from __future__ import annotations

import os
import re

from .config import setting

# --- Partitions -------------------------------------------------------------
# max_seconds = TimeLimit renvoye par `sinfo`.
# `nodes_by_arch` : chaque partition n'expose qu'un sous-ensemble du parc.
# Ignorer ce detail produit des jobs qui restent indefiniment en attente, par
# exemple 50 noeuds armgpu sur `long` qui n'en compte que 40.
# Releve par `sinfo -h -p <partition> -N` le 2026-08-20.
PARTITIONS: dict[str, dict] = {
    "instant": {
        "max_seconds": 3_600,
        "is_default": True,
        "note": "partition par defaut, 1 h maximum",
        "nodes_by_arch": {"x64cpu": 44, "armgpu": 58},
    },
    "short": {
        "max_seconds": 86_400,
        "is_default": False,
        "note": "1 jour maximum",
        "nodes_by_arch": {"x64cpu": 43, "armgpu": 56},
    },
    "long": {
        "max_seconds": 30 * 86_400,
        "is_default": False,
        "note": "30 jours maximum, file plus lente",
        "nodes_by_arch": {"x64cpu": 24, "armgpu": 40},
    },
}

# --- Limites du compte utilisateur ------------------------------------------
# Seuils indicatifs configurables : ils ne remplacent pas les limites reelles
# de l'association Slurm. Utiliser selfcheck pour relever celles du compte.
USER_MAX_CPUS = int(os.environ.get("ROMEO_MAX_CPUS", "0"))
USER_MAX_GPUS = int(os.environ.get("ROMEO_MAX_GPUS", "0"))
USER_MAX_JOBS = int(os.environ.get("ROMEO_MAX_JOBS", "0"))

# --- Quotas de stockage -----------------------------------------------------
# Valeurs par defaut documentees, aussi observees le 2026-08-20.
# Les relevements sont propres a chaque espace, utilisateur et projet.
QUOTA_SOFT_GB = 15
QUOTA_HARD_GB = 20
QUOTA_GRACE_DAYS = 7

# Ordre croissant de limite de temps : on prend toujours la plus petite partition
# qui convient, car la file y est plus rapide.
PARTITION_ORDER = ["instant", "short", "long"]

# --- Familles de noeuds -----------------------------------------------------
# `feature` est la valeur a passer a --constraint.
ARCHS: dict[str, dict] = {
    "x64cpu": {
        "feature": "x64cpu",
        "uname": "x86_64",
        "nodes": "romeo-c[001-040,101-104]",
        "node_count": 44,
        # Fonction shell qui source l'installation Spack propre a cette
        # architecture. C'est la voie officielle pour charger des logiciels.
        "env_loader": "romeo_load_x64cpu_env",
        "spack_root": "/apps/2025/manual_install/spack-x64cpu-1.0.x",
        "cpus_per_node": 192,
        # romeo-c[001-040] : 1 160 629 Mo ; romeo-c[101-104] : 1 547 701 Mo.
        # On valide sur la valeur basse pour ne pas produire de job impossible
        # a placer sur la majorite du parc.
        "mem_mb_per_node": 1_160_629,
        "mem_mb_max_node": 1_547_701,
        "gpus_per_node": 0,
        "gpu_model": None,
    },
    "armgpu": {
        "feature": "armgpu",
        "uname": "aarch64",
        "nodes": "romeo-a[001-058]",
        "node_count": 58,
        "env_loader": "romeo_load_armgpu_env",
        "spack_root": "/apps/2025/manual_install/spack-armgpu-1.0.x",
        "cpus_per_node": 288,
        "mem_mb_per_node": 820_802,
        "mem_mb_max_node": 820_802,
        "gpus_per_node": 4,
        # `h100` est l'identifiant GRES declare dans SLURM, a utiliser tel quel
        # dans --gres. Le materiel reel est un GH200 120 Go (Grace Hopper,
        # capacite de calcul sm_90), verifie par nvidia-smi le 2026-08-20.
        "gpu_model": "h100",
        "gpu_hardware": "NVIDIA GH200 120GB (Grace Hopper, sm_90)",
    },
}

DEFAULT_ACCOUNT = setting("ROMEO_ACCOUNT").strip()
DEFAULT_QOS = setting("ROMEO_QOS", "normal")
#: Alias SSH du noeud de login. `romeo1` est son nom reel ; garder `romeo`
#: comme defaut obligeait a inventer un alias qui ne correspond a rien.
DEFAULT_HOST = setting("ROMEO_HOST", "romeo1")

MODULES_KNOWN = [
    "cuda/12.6",
    "nvhpc/nvhpc/24.11",
    "nvhpc/nvhpc-hpcx-cuda12/24.11",
    "openmpi/aarch64/4.1.7",
    "openmpi/aarch64/4.1.7-cuda",
    "openmpi/gnu/4.1.7",
    "openmpi/aocc-4.2.0/4.1.7",
    "aocc-compiler-4.2.0",
    "aocl-4.2.0",
]

#: Outils absents du PATH mais disponibles via Spack, une fois l'environnement
#: de l'architecture charge. Verifie le 2026-08-20 : `spack find` remonte 562
#: paquets uniques sur x64cpu et 322 sur armgpu.
TOOLS_VIA_SPACK = {
    "conda": "anaconda3",
    "anaconda": "anaconda3",
    "apptainer": "apptainer",
    "singularity": "apptainer",
    "cuda": "cuda (12.3 a 13.0 selon l'architecture)",
}

#: Outils reellement introuvables, y compris dans Spack.
MISSING_TOOLS = ["seff"]


class ClusterError(ValueError):
    """Contrainte cluster violee. Le message est redige pour le modele."""


def require_account(value: str | None = None) -> str:
    """Exige un projet explicite avant de preparer une allocation Slurm."""
    account = DEFAULT_ACCOUNT if value is None else value
    if not account or account.upper() in {"VOTRE_PROJET", "YOUR_PROJECT", "R000000"}:
        raise ClusterError(
            "Projet ROMEO absent : executer `python -m romeo_mcp configure "
            "--account VOTRE_PROJET` avec le code du projet autorise, puis "
            "relancer le client MCP. ROMEO_ACCOUNT permet aussi de le definir."
        )
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", account):
        raise ClusterError("compte Slurm invalide : utiliser un identifiant de projet simple.")
    return account


# --- Duree ------------------------------------------------------------------
_DUR_SUFFIX = re.compile(r"^(\d+(?:\.\d+)?)\s*([smhdSMHD])$")
_DUR_CLOCK = re.compile(r"^(?:(\d+)-)?(\d+):(\d{1,2})(?::(\d{1,2}))?$")
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3_600, "d": 86_400}


def parse_duration(value: str | int) -> int:
    """Convertit une duree en secondes.

    Accepte un entier (des minutes, convention SLURM), les suffixes courts
    ``2h`` / ``30m`` / ``1d``, ainsi que les formats horloge ``1:30:00``,
    ``30:00`` (MM:SS) et ``2-00:00:00`` (D-HH:MM:SS).
    """
    if isinstance(value, int):
        return value * 60
    text = str(value).strip()
    if not text:
        raise ClusterError("duree vide")
    if text.isdigit():
        return int(text) * 60

    match = _DUR_SUFFIX.match(text)
    if match:
        return int(float(match.group(1)) * _UNIT_SECONDS[match.group(2).lower()])

    match = _DUR_CLOCK.match(text)
    if match:
        days, first, second, third = match.groups()
        total_days = int(days or 0)
        if third is None:
            hours, minutes, seconds = 0, int(first), int(second)
        else:
            hours, minutes, seconds = int(first), int(second), int(third)
        return total_days * 86_400 + hours * 3_600 + minutes * 60 + seconds

    raise ClusterError(
        "duree illisible : {!r}. Formats acceptes : 2h, 30m, 1d, 1:30:00, "
        "2-00:00:00, ou un entier de minutes.".format(value)
    )


def format_slurm_time(seconds: int) -> str:
    """Rend une duree au format ``D-HH:MM:SS`` attendu par ``--time``."""
    days, rest = divmod(int(seconds), 86_400)
    hours, rest = divmod(rest, 3_600)
    minutes, secs = divmod(rest, 60)
    if days:
        return "{}-{:02d}:{:02d}:{:02d}".format(days, hours, minutes, secs)
    return "{:02d}:{:02d}:{:02d}".format(hours, minutes, secs)


def pick_partition(seconds: int) -> str:
    """Plus petite partition dont la limite de temps couvre ``seconds``."""
    for name in PARTITION_ORDER:
        if seconds <= PARTITIONS[name]["max_seconds"]:
            return name
    raise ClusterError(
        "{} depasse la limite de 30 jours de la partition long. Decoupe le "
        "calcul en jobs chaines avec reprise sur checkpoint.".format(
            format_slurm_time(seconds)
        )
    )


_ARCH_ALIASES = {
    "arm": "armgpu",
    "aarch64": "armgpu",
    "gpu": "armgpu",
    "armgpu": "armgpu",
    "grace": "armgpu",
    "x86": "x64cpu",
    "x86_64": "x64cpu",
    "x64": "x64cpu",
    "cpu": "x64cpu",
    "x64cpu": "x64cpu",
}


def resolve_arch(arch: str | None, gpus: int) -> str:
    """Determine la famille de noeuds. Un job GPU va forcement sur ``armgpu``."""
    if not arch:
        return "armgpu" if gpus > 0 else "x64cpu"

    key = str(arch).strip().lower()
    if key not in _ARCH_ALIASES:
        raise ClusterError(
            "architecture inconnue : {!r}. Valeurs acceptees : x64cpu (CPU "
            "x86_64) ou armgpu (aarch64 + 4x H100).".format(arch)
        )
    resolved = _ARCH_ALIASES[key]
    if gpus > 0 and resolved == "x64cpu":
        raise ClusterError(
            "arch=x64cpu est incompatible avec gpus>0 : les seuls GPU de ROMEO "
            "sont les H100 des noeuds armgpu (aarch64). Passe arch=armgpu ou "
            "gpus=0."
        )
    return resolved


def cheatsheet() -> str:
    """Aide-memoire ROMEO au format Markdown, servi comme ressource MCP."""
    lines = [
        "# ROMEO (URCA) - aide-memoire",
        "",
        "Hote SSH `{}` - compte SLURM `{}` - QOS `{}`.".format(
            DEFAULT_HOST, DEFAULT_ACCOUNT, DEFAULT_QOS
        ),
        "Ordonnanceur SLURM sur RHEL 9.6. **Le noeud de login est en x86_64.**",
        "",
        "## Partitions",
        "",
        "| Partition | Limite de temps | Noeuds x64cpu | Noeuds armgpu |",
        "|---|---|---|---|",
    ]
    for name in PARTITION_ORDER:
        partition = PARTITIONS[name]
        star = " (defaut)" if partition["is_default"] else ""
        counts = partition["nodes_by_arch"]
        lines.append(
            "| `{}`{} | {} | {} | {} |".format(
                name,
                star,
                format_slurm_time(partition["max_seconds"]),
                counts["x64cpu"],
                counts["armgpu"],
            )
        )
    lines.append("")
    lines.append(
        "Chaque partition n'expose qu'une partie du parc : demander plus de "
        "noeuds qu'elle n'en compte laisse le job en attente indefiniment."
    )

    lines += [
        "",
        "## Familles de noeuds",
        "",
        "| Contrainte | Architecture | Noeuds | CPU | RAM | GPU |",
        "|---|---|---|---|---|---|",
    ]
    for key, spec in ARCHS.items():
        gpu = (
            "{}x {}".format(spec["gpus_per_node"], spec["gpu_model"])
            if spec["gpus_per_node"]
            else "-"
        )
        lines.append(
            "| `{}` | {} | {} | {} | {} Go | {} |".format(
                key,
                spec["uname"],
                spec["nodes"],
                spec["cpus_per_node"],
                spec["mem_mb_per_node"] // 1024,
                gpu,
            )
        )

    lines += [
        "",
        "Le materiel GPU est un **NVIDIA GH200** (Grace Hopper, sm_90) offrant",
        "**97 871 Mio de VRAM** par GPU : compile avec `-arch=sm_90`. La",
        "documentation officielle demande `--gpus-per-node=N`, ce que genere",
        "`submit_job` ; `--gres=gpu:h100:N` fonctionne aussi (verifie), `h100`",
        "etant l'identifiant GRES declare dans SLURM.",
        "",
        "## Memoire obligatoire",
        "",
        "ROMEO refuse toute soumission sans `--mem` (`Memory resource is",
        "missing`). L'outil `submit_job` derive automatiquement une part",
        "proportionnelle aux coeurs demandes quand `mem_gb` n'est pas precise.",
        "",
        "## Piege numero un : la double architecture",
        "",
        "Le noeud de login est **x86_64** mais les noeuds GPU sont **aarch64**.",
        "Tout artefact compile ou installe depuis le login (pip install, make,",
        "nvcc) produit du binaire x86 qui echouera sur les noeuds `armgpu`.",
        "Utilise l'outil `build_on_node` : il compile sur un noeud de la bonne",
        "architecture via srun, jamais sur le login.",
        "",
        "## Stockage",
        "",
        "- `$HOME` : code et sources.",
        "- `/scratch_p/$USER` : espace de travail des jobs, optimise pour les calculs.",
        "- `/project/<code_projet>` : espace partage de l'equipe.",
        "- `/apps` : installations systeme, en lecture seule.",
        "",
        "Quotas par defaut : {} Go souples / {} Go stricts ; les valeurs".format(
            QUOTA_SOFT_GB, QUOTA_HARD_GB
        ),
        "effectives peuvent differer par espace apres un relevement. Consulter romeo_quota.",
        "",
        "Depasser le quota souple ouvre un delai de grace de {} jours ; passe ce".format(
            QUOTA_GRACE_DAYS
        ),
        "delai, l'ecriture est bloquee meme sous le quota strict. Verifie avec",
        "l'outil `romeo_quota`, qui interroge `mmlsquota` et non `df` (`df`",
        "montre les 2,8 Po du systeme de fichiers, pas ta part).",
        "",
        "## Limites du compte",
        "",
        "Seuils locaux : CPU {}, GPU {}, jobs soumis {}.".format(
            USER_MAX_CPUS or "non configure", USER_MAX_GPUS or "non configure",
            USER_MAX_JOBS or "non configure"
        ),
        "Aucun quota personnel n'est suppose. Verifier les associations Slurm avec selfcheck.",
        "",
        "## Modules disponibles (extrait)",
        "",
    ]
    lines += ["- `{}`".format(name) for name in MODULES_KNOWN]
    lines += [
        "",
        "Attention : `openmpi/aarch64/*` pour `armgpu`, `openmpi/gnu/*` pour `x64cpu`.",
        "",
        "## Charger des logiciels : la voie officielle",
        "",
        "Au-dela des modules, ROMEO fournit **Spack**, propre a chaque",
        "architecture. Deux fonctions shell chargent l'environnement :",
        "",
        "- `romeo_load_x64cpu_env` puis `spack load <paquet>` (562 paquets)",
        "- `romeo_load_armgpu_env` puis `spack load <paquet>` (322 paquets)",
        "",
        "Ces fonctions sourcent une installation Spack differente selon",
        "l'architecture : charger la mauvaise donne des binaires inutilisables.",
        "`submit_job` et `build_on_node` s'en chargent via leur parametre",
        "`spack_packages`. Cherche un paquet avec l'outil `romeo_software`.",
        "",
        "Consequence : `conda` (paquet `anaconda3`), `apptainer` et plusieurs",
        "versions de `cuda` sont disponibles, contrairement a ce que laisse",
        "croire un `command -v` sur le noeud de login.",
        "",
        "## Outils reellement absents",
        "",
        ", ".join("`" + tool + "`" for tool in MISSING_TOOLS) + ".",
        "L'outil `job_efficiency` recalcule les metriques de seff depuis sacct.",
        "",
        "## Regles d'usage",
        "",
        "1. Aucun calcul sur le noeud de login : `submit_job` ou `build_on_node`.",
        "2. Demande la plus petite partition qui couvre ton temps d'execution.",
        "3. Relis `job_efficiency` apres un job pour recalibrer le run suivant.",
    ]
    return "\n".join(lines)
