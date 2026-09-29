"""Interface MCP des services, environnements et executions explicites."""
from __future__ import annotations
import re
from typing import Any
from pydantic import TypeAdapter
from .cluster import parse_duration
from .guard import GuardError, check_login_command, check_path
from .templates import SHM_TOTAL_GO, preambule_staging_shm
from .slurm import JobSpec
from .ssh import SSHError, SSHTimeout, session
from .noyau import MUTATING, DESTRUCTIVE, READ_ONLY, _error, _sh, outil
from .plans import prepare_spec, submit_prepared
from .service_models import ServiceConfig
from . import services, python_operations


@outil(annotations=MUTATING, description=(
    "Prepare un service dans un venv existant, sans installation ni soumission. "
    "Enregistre localement le script exact, les ressources et la configuration pour 24 h. "
    "Jupyter et vLLM generent leur jeton prive au demarrage. Aucun tunnel n'est ouvert."))
def service_prepare(config: ServiceConfig, time_limit: str = "2h", arch: str = "armgpu",
                    gpus_per_node: int = 0, cpus_per_task: int = 16, workdir: str | None = None,
                    spack_packages: list[str] | None = None) -> dict[str, Any]:
    config = TypeAdapter(ServiceConfig).validate_python(config)
    return services.prepare_service(config.model_dump(), time_limit, arch, gpus_per_node,
                                    cpus_per_task, workdir, spack_packages)


@outil(annotations=MUTATING, description="Soumet le service exact prepare ; exige confirm=true. Rend service_id et job_id sans attendre le noeud ni l'ouverture du service.")
def service_start(plan_id: str, confirm: bool = False) -> dict[str, Any]:
    return submit_prepared("service", plan_id, confirm)


@outil(annotations=READ_ONLY, description="Lit Slurm et sonde HTTP le service une seule fois, sans allocation : waiting, starting, ready, stopped, failed ou unknown. Ne bloque pas en attente de disponibilite.")
def service_status(service_id: str) -> dict[str, Any]:
    return services.service_status(service_id)


@outil(annotations=READ_ONLY, description="Pour un service pret, fournit URL, authentification et commande SSH. Lit le jeton prive si necessaire ; n'ouvre aucun tunnel.")
def service_connection_info(service_id: str, local_port: int = 8888) -> dict[str, Any]:
    return services.connection_info(service_id, local_port)


@outil(annotations=MUTATING, description="Demande explicitement l'arret du service par scancel. Verifie ensuite sa fin avec service_status.")
def service_stop(service_id: str) -> dict[str, Any]:
    return services.stop_service(service_id)


@outil(annotations=MUTATING, description="Prepare localement la creation d'un venv sur la bonne architecture. Fournis spack_packages avec une specification Python non ambigue (version, compilateur ou empreinte), choisie via romeo_software ; le nom python seul est refuse. Le parent doit exister ; la creation refusera une cible existante. Aucune installation de paquet applicatif.")
def python_env_prepare(env_path: str, arch: str = "armgpu", time_limit: str = "15m",
                       spack_packages: list[str] | None = None) -> dict[str, Any]:
    return python_operations.prepare_environment(env_path, arch, time_limit, spack_packages)


@outil(annotations=MUTATING, description="Soumet la creation du venv exact prepare. Exige confirm=true, rend un job_id sans attendre.")
def python_env_create(plan_id: str, confirm: bool = False) -> dict[str, Any]:
    return submit_prepared("python_env", plan_id, confirm)


@outil(annotations=MUTATING, description="Prepare localement l'installation de paquets dans un venv existant, sur un noeud de la meme architecture. N'installe rien pendant la preparation.")
def python_packages_prepare(env_path: str, packages: list[str], arch: str = "armgpu",
                            time_limit: str = "30m", upgrade: bool = False) -> dict[str, Any]:
    return python_operations.prepare_packages(env_path, packages, arch, time_limit, upgrade)


@outil(annotations=MUTATING, description="Soumet l'installation exacte preparee dans le venv. Exige confirm=true ; rend un job_id sans attendre.")
def python_packages_install(plan_id: str, confirm: bool = False) -> dict[str, Any]:
    return submit_prepared("python_packages", plan_id, confirm)


@outil(annotations=MUTATING, description="Prepare localement une roue Python pour l'architecture cible. source est une specification pip ou une URL git+https. Aucune compilation pendant la preparation.")
def python_wheel_prepare(source: str, arch: str = "armgpu", time_limit: str = "45m",
                         cpus_per_task: int = 32, with_gpu: bool = False,
                         spack_packages: list[str] | None = None,
                         no_build_isolation: bool = False) -> dict[str, Any]:
    return python_operations.prepare_wheel(source, arch, time_limit, cpus_per_task,
                                           with_gpu, spack_packages, no_build_isolation)


@outil(annotations=MUTATING, description="Soumet la construction exacte de roue preparee. Exige confirm=true ; rend un job_id sans attendre.")
def python_wheel_build(plan_id: str, confirm: bool = False) -> dict[str, Any]:
    return submit_prepared("python_wheel", plan_id, confirm)


@outil(annotations=MUTATING, description="Prepare localement une allocation de mise au point, limitee a une heure. Aucun noeud n'est reserve avant cluster_allocation_start.")
def cluster_allocation_prepare(time_limit: str = "30m", arch: str = "armgpu",
                               gpus_per_node: int = 1, cpus_per_task: int = 16) -> dict[str, Any]:
    seconds = parse_duration(time_limit)
    if not 300 <= seconds <= 3600:
        raise ValueError("La reservation doit durer de 5 minutes a une heure.")
    return prepare_spec("allocation", JobSpec(name="mcp-debug", command="sleep {}".format(seconds),
        time=time_limit, arch=arch, gpus_per_node=gpus_per_node, cpus_per_task=cpus_per_task))


@outil(annotations=MUTATING, description="Soumet l'allocation preparee, exige confirm=true, rend immediatement job_id. Consulte job_status puis cluster_allocation_connection_info ; annule avec cancel_job.")
def cluster_allocation_start(plan_id: str, confirm: bool = False) -> dict[str, Any]:
    return submit_prepared("allocation", plan_id, confirm)


@outil(annotations=READ_ONLY, description="Fournit la commande de shell pour une allocation en cours. Ne lance aucun shell ni nouvelle allocation.")
def cluster_allocation_connection_info(job_id: str) -> dict[str, Any]:
    state = services.allocation_state(session(), job_id)
    if state.get("slurm_state") != "RUNNING":
        return {**state, "ok": False, "error": "L'allocation doit etre en cours."}
    return {**state, "shell_command": "srun --jobid={} --pty bash -l".format(job_id), "shell_opened": False}


@outil(annotations=MUTATING, description="Expert : prepare localement des commandes shell arbitraires pour un noeud de calcul. Aucun lancement pendant la preparation ; les commandes seront executees exactement telles que relues.")
def compute_command_prepare(commands: list[str], arch: str = "armgpu", workdir: str | None = None,
                            modules: list[str] | None = None, spack_packages: list[str] | None = None,
                            time_limit: str = "15m", cpus_per_task: int = 16, with_gpu: bool = False) -> dict[str, Any]:
    if not commands or any(not c.strip() for c in commands):
        raise ValueError("Fournis des commandes non vides.")
    return prepare_spec("command", JobSpec(name="mcp-command", command="\n".join(commands), time=time_limit,
        arch=arch, workdir=workdir, modules=modules or [], spack_packages=spack_packages or [],
        cpus_per_task=cpus_per_task, gpus_per_node=int(with_gpu)))


@outil(annotations=DESTRUCTIVE, description="Expert : soumet les commandes arbitraires exactes du plan. Exige confirm=true ; rend immediatement job_id.")
def compute_command_run(plan_id: str, confirm: bool = False) -> dict[str, Any]:
    return submit_prepared("command", plan_id, confirm)


@outil(
    annotations=DESTRUCTIVE,
    description=(
        "Execute une commande COURTE et LEGERE sur le noeud de login "
        "(inspection, git, ls, grep). Les compilations, installations et "
        "calculs sont refuses par defaut : le noeud de login est partage par "
        "tout le laboratoire. `allow_heavy=true` leve ce refus pour les cas que "
        "la documentation ROMEO autorise explicitement, comme un `pip install` "
        "en environnement virtuel a destination du x86_64. Delai maximal 20 s."
    ),
)
def login_command_run(
    command: str,
    timeout_seconds: int = 15,
    cwd: str | None = None,
    allow_heavy: bool = False,
) -> dict[str, Any]:
    """Echappatoire pour ce qu'aucun outil dedie ne couvre."""
    s = session()
    try:
        check_login_command(command, allow_heavy=allow_heavy)
    except GuardError as exc:
        return _error(str(exc), refused=True)

    budget = max(1, min(int(timeout_seconds), 20))
    try:
        target = check_path(cwd, s.home, s.scratch, s.path_aliases) if cwd else None
        result = _sh(s, command, timeout=budget, cwd=target, max_chars=10_000)
    except GuardError as exc:
        return _error(str(exc))
    except SSHTimeout as exc:
        return _error(str(exc), refused=False)
    except SSHError as exc:
        return _error(str(exc))

    return {
        "ok": result.ok,
        "exit_code": result.rc,
        "duration_seconds": round(result.duration, 2),
        "truncated": result.truncated,
        "output": result.stdout,
    }

@outil(
    annotations=READ_ONLY,
    description=(
        "Insere la mise en cache d'un jeu de donnees en memoire vive dans un "
        "script sbatch existant, que ce serveur n'a pas genere. Rend le script "
        "modifie sans rien ecrire : a toi de le relire puis de le deposer. "
        "Pour un job cree ici, prefere job_prepare(stage_archive=...)."
    ),
)
def inject_io_staging(
    script: str, dataset_archive: str, variable: str = "DATASET_DIR"
) -> dict[str, Any]:
    """Greffe le preambule de mise en cache apres l'en-tete sbatch."""
    if not script.strip():
        return _error("script vide")
    if not dataset_archive.strip():
        return _error("chemin d'archive vide")
    if not re.match(r"^[\w./$-]{1,4096}$", dataset_archive.strip()):
        return _error("chemin d'archive suspect : {!r}".format(dataset_archive))

    lignes = script.splitlines()
    # Le preambule doit venir apres la derniere directive #SBATCH, sinon SLURM
    # cesse de lire l'en-tete a la premiere ligne executable rencontree.
    dernier = -1
    for index, ligne in enumerate(lignes):
        depouillee = ligne.strip()
        if depouillee.startswith("#SBATCH"):
            dernier = index
        elif depouillee and not depouillee.startswith("#") and dernier >= 0:
            break

    if dernier < 0:
        return _error(
            "aucune directive #SBATCH trouvee : ce script ne ressemble pas a "
            "un fichier de soumission."
        )

    bloc = [""] + preambule_staging_shm(dataset_archive.strip(), variable)
    modifie = lignes[: dernier + 1] + bloc + lignes[dernier + 1 :]

    return {
        "ok": True,
        "archive": dataset_archive.strip(),
        "variable": variable,
        "insere_apres_ligne": dernier + 1,
        "script": "\n".join(modifie) + "\n",
        "rappels": [
            "Fais pointer les chemins de ton entrainement sur ${}.".format(variable),
            "`--mem` doit couvrir la taille decompressee : /dev/shm est impute "
            "au cgroup memoire du job.",
            "/dev/shm fait {} Go et il est partage entre les jobs du noeud ; "
            "verifie l'espace libre avant un jeu de donnees volumineux.".format(
                SHM_TOTAL_GO
            ),
            "Le nettoyage est assure par un piege EXIT ; ne le retire pas.",
        ],
    }
