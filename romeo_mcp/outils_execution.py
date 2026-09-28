"""Executer ailleurs que sur le noeud de login.

Le login est en x86_64 alors que les noeuds GPU sont en aarch64 : compiler ou
installer depuis le login produit des binaires inutilisables. Ces outils
deportent le travail sur un noeud de la bonne architecture.
"""

from __future__ import annotations

import posixpath
import re
import secrets
import shlex
from typing import Any
from .cluster import ARCHS, ClusterError, format_slurm_time, require_account
from .guard import GuardError, check_login_command, check_path
from .templates import SERVICES, SHM_TOTAL_GO, commande_tunnel, preambule_staging_shm
from .slurm import JobSpec, plan_job
from .ssh import SSHError, SSHTimeout, session
from .noyau import (
    MAX_BUILD_SECONDS,
    MUTATING,
    READ_ONLY,
    _attendre_noeud,
    _duree_job,
    _error,
    _sh,
    _soumettre_sbatch,
    _wheelhouse,
    outil,
)


# =============================================================================
# Construction sur la bonne architecture
# =============================================================================
@outil(
    annotations=MUTATING,
    description=(
        "Compile ou installe sur un noeud de calcul de l'architecture voulue, "
        "via srun. INDISPENSABLE pour cibler les noeuds GPU : ils sont en "
        "aarch64 alors que le noeud de login est en x86_64, donc tout artefact "
        "produit sur le login y est inutilisable. Synchrone, plafonne a 15 min."
    ),
)
def build_on_node(
    commands: list[str],
    arch: str = "armgpu",
    workdir: str | None = None,
    modules: list[str] | None = None,
    spack_packages: list[str] | None = None,
    minutes: int = 15,
    cpus: int = 16,
    with_gpu: bool = False,
) -> dict[str, Any]:
    """Execute une suite de commandes de construction sur un noeud dedie."""
    account = require_account()
    s = session()
    if not commands:
        return _error("aucune commande a executer")

    key = arch.strip().lower()
    if key not in ARCHS:
        return _error(
            "architecture inconnue : {!r}. Valeurs : x64cpu, armgpu.".format(arch)
        )
    node = ARCHS[key]
    if with_gpu and not node["gpus_per_node"]:
        return _error("la famille {} n'a pas de GPU.".format(key))

    minutes = max(1, min(int(minutes), 60))
    cpus = max(1, min(int(cpus), node["cpus_per_node"]))

    try:
        target_dir = (
            check_path(workdir, s.home, s.scratch, s.path_aliases) if workdir else s.scratch
        )
    except GuardError as exc:
        return _error(str(exc))

    script_lines = ["set -euo pipefail"]
    if modules:
        script_lines.append("module purge")
        script_lines += ["module load {}".format(m) for m in modules]
    # Sans l'environnement de l'architecture, le noeud n'a acces a aucun
    # logiciel, pas meme a spack.
    script_lines.append(node["env_loader"])
    script_lines += ["spack load {}".format(p) for p in (spack_packages or [])]
    script_lines += [
        'echo "[romeo-mcp] construction sur $(hostname) ($(uname -m))"',
        *commands,
    ]
    remote_script = "\n".join(script_lines)

    script_path = posixpath.join(target_dir, ".romeo-mcp-build.sh")
    try:
        s.write_file(script_path, remote_script, mode="700")
    except (SSHError, SSHTimeout) as exc:
        return _error(str(exc))

    srun = [
        "srun",
        "--account={}".format(account),
        "--partition={}".format("instant" if minutes <= 60 else "short"),
        "--constraint={}".format(node["feature"]),
        "--time={}".format(format_slurm_time(minutes * 60)),
        "--nodes=1",
        "--ntasks=1",
        "--cpus-per-task={}".format(cpus),
        # ROMEO exige --mem sur toute allocation : part proportionnelle aux coeurs.
        "--mem={}G".format(
            max(1, (node["mem_mb_per_node"] // 1024) * cpus // node["cpus_per_node"])
        ),
        "--job-name=mcp-build",
    ]
    if with_gpu:
        srun.append("--gpus-per-node=1")
    srun += ["bash", "-l", shlex.quote(script_path)]

    # Marge locale au-dela de la limite SLURM : l'attente en file compte aussi.
    budget = min(minutes * 60 + 180, MAX_BUILD_SECONDS)
    try:
        result = _sh(
            s, " ".join(srun), timeout=budget, cwd=target_dir, max_chars=20_000
        )
    except SSHTimeout:
        return _error(
            "la construction a depasse {} s (attente en file comprise). "
            "Relance-la comme un job normal via job_prepare, puis suis-la avec "
            "job_log_tail.".format(budget),
            script_path=script_path,
        )
    except SSHError as exc:
        return _error(str(exc), script_path=script_path)

    return {
        "ok": result.ok,
        "arch": key,
        "uname_expected": node["uname"],
        "exit_code": result.rc,
        "workdir": target_dir,
        "script_path": script_path,
        "duration_seconds": round(result.duration, 1),
        "output": result.stdout or "(aucune sortie)",
    }

# =============================================================================
# Echappatoire encadree
# =============================================================================
@outil(
    annotations=MUTATING,
    description=(
        "Execute une commande COURTE et LEGERE sur le noeud de login "
        "(inspection, git, ls, grep). Les compilations, installations et "
        "calculs sont refuses par defaut : le noeud de login est partage par "
        "tout le laboratoire. `allow_heavy=true` leve ce refus pour les cas que "
        "la documentation ROMEO autorise explicitement, comme un `pip install` "
        "en environnement virtuel a destination du x86_64. Delai maximal 20 s."
    ),
)
def run_login_command(
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
    annotations=MUTATING,
    description=(
        "Lance un service web sur un noeud de calcul (JupyterLab, TensorBoard, "
        "vLLM, MLflow) et rend la commande de pont SSH exacte a executer en "
        "local pour y acceder. Attend l'affectation du noeud pour pouvoir "
        "composer cette commande."
    ),
)
def launch_interactive_service(
    service: str,
    port: int = 8888,
    local_port: int = 0,
    minutes: int = 120,
    time_limit: str | None = None,
    gpus_per_node: int = 0,
    cpus_per_task: int = 16,
    arch: str | None = None,
    workdir: str | None = None,
    logdir: str = "",
    model: str = "",
    spack_packages: list[str] | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Soumet le service puis compose le pont SSH vers le noeud alloue."""
    s = session()
    cle = (service or "").strip().lower()
    if cle not in SERVICES:
        return _error(
            "service inconnu : {!r}. Valeurs : {}.".format(
                service, ", ".join(SERVICES)
            )
        )
    modele = SERVICES[cle]
    port = int(port)
    if not (1024 <= port <= 65535):
        return _error("port hors plage utilisateur : {}".format(port))
    local_port = int(local_port) or port

    if cle == "vllm" and not model:
        return _error("le service vLLM exige un `model` a servir.")
    if cle == "tensorboard" and not logdir:
        return _error("le service TensorBoard exige un `logdir`.")

    commande = modele["commande"].format(port=port, logdir=logdir, model=model)
    spec = JobSpec(
        name="mcp-{}".format(cle),
        command=commande,
        time=_duree_job(minutes, time_limit, 24 * 60),
        cpus_per_task=cpus_per_task,
        gpus_per_node=gpus_per_node,
        arch=arch,
        workdir=workdir,
        spack_packages=(spack_packages or []) + list(modele["paquets"]),
    )
    try:
        if workdir:
            spec.workdir = check_path(workdir, s.home, s.scratch, s.path_aliases)
        plan = plan_job(spec, s.scratch)
    except (ClusterError, GuardError, SSHError, SSHTimeout) as exc:
        return _error(str(exc))

    if not confirm:
        return {
            "ok": True, "submitted": False, "mode": "simulation",
            "service": modele["libelle"], "note": modele["note"],
            "commande_service": commande,
            "script": plan.script,
            "next_step": "Rappelle avec confirm=true pour lancer le service.",
        }

    soumission = _soumettre_sbatch(s, plan, spec.name, note="service {}".format(cle))
    if not soumission["ok"]:
        return soumission
    job_id = soumission["job_id"]

    noeud = _attendre_noeud(s, job_id)
    reponse = {
        "ok": True, "submitted": True, "job_id": job_id,
        "service": modele["libelle"], "port_distant": port,
        "note": modele["note"], "workdir": plan.workdir,
    }
    if not noeud:
        reponse["node"] = None
        reponse["next_step"] = (
            "Le noeud n'est pas encore affecte. Rappelle job_status('{}') puis "
            "compose le pont : ssh -N -L {}:<noeud>:{} {}".format(
                job_id, local_port, port, s.host
            )
        )
        return reponse

    reponse["node"] = noeud
    reponse["tunnel"] = commande_tunnel(s.host, noeud, port, local_port)
    reponse["url"] = "http://localhost:{}".format(local_port)
    reponse["next_step"] = (
        "Execute la commande `tunnel` dans un terminal LOCAL, en la laissant "
        "ouverte, puis ouvre `url` dans ton navigateur. Pour JupyterLab, le "
        "jeton figure dans la sortie du job : job_log_tail('{}').".format(job_id)
    )
    return reponse

@outil(
    annotations=MUTATING,
    description=(
        "Reserve un noeud de calcul pour de la mise au point interactive "
        "(compilation, profilage, essais). Rend la commande a executer pour "
        "obtenir un shell dessus. Utile pour tester sur aarch64 sans passer "
        "par un aller-retour de job batch."
    ),
)
def allocate_debug_node(
    minutes: int = 30,
    time_limit: str | None = None,
    arch: str = "armgpu",
    gpus_per_node: int = 1,
    cpus_per_task: int = 16,
    confirm: bool = False,
) -> dict[str, Any]:
    """Reserve un noeud qui reste disponible le temps demande."""
    s = session()
    minutes = max(5, min(int(minutes), 60))
    spec = JobSpec(
        name="mcp-debug",
        command='echo "[romeo-mcp] noeud reserve pour {} min"; sleep {}'.format(
            minutes, minutes * 60
        ),
        time=_duree_job(minutes, time_limit, 60),
        arch=arch,
        gpus_per_node=gpus_per_node,
        cpus_per_task=cpus_per_task,
    )
    try:
        plan = plan_job(spec, s.scratch)
    except (ClusterError, SSHError, SSHTimeout) as exc:
        return _error(str(exc))

    if not confirm:
        return {
            "ok": True, "submitted": False, "mode": "simulation",
            "resolved": {"arch": plan.arch, "partition": plan.partition,
                         "minutes": minutes},
            "next_step": "Rappelle avec confirm=true pour reserver le noeud.",
        }

    # Cette reservation etait le seul site a ne pas s'enregistrer : le job
    # devenait invisible de `list_jobs` cote registre.
    soumission = _soumettre_sbatch(
        s, plan, "mcp-debug", note="reservation interactive de {} min".format(minutes)
    )
    if not soumission["ok"]:
        return soumission
    job_id = soumission["job_id"]
    noeud = _attendre_noeud(s, job_id, budget=240)
    return {
        "ok": True, "job_id": job_id, "node": noeud,
        "arch": plan.arch, "minutes": minutes,
        "shell": "srun --jobid={} --pty bash -l".format(job_id),
        "next_step": (
            "Depuis un terminal connecte a ROMEO, execute la commande `shell` "
            "pour obtenir un interpreteur sur le noeud. Libere la reservation "
            "avec cancel_job('{}') des que tu as fini : elle consomme des "
            "heures de calcul.".format(job_id)
        ),
    }

@outil(
    annotations=MUTATING,
    description=(
        "Compile un paquet Python en roue binaire sur un noeud de la bonne "
        "architecture et la depose dans un depot local. Evite de recompiler "
        "les extensions C++/CUDA (deepspeed, flash-attn, bitsandbytes) a chaque "
        "nouvel environnement. Les roues ainsi produites sont ensuite trouvees "
        "automatiquement par romeo_pip_install."
    ),
)
def build_wheel(
    package: str,
    git_url: str = "",
    build_flags: str = "",
    arch: str = "armgpu",
    minutes: int = 45,
    cpus_per_task: int = 32,
    with_gpu: bool = False,
    spack_packages: list[str] | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Produit une roue binaire pour l'architecture cible."""
    s = session()
    cle = arch.strip().lower()
    if cle not in ARCHS:
        return _error("architecture inconnue : {!r}.".format(arch))
    if not package.strip() and not git_url.strip():
        return _error("precise au moins `package` ou `git_url`.")

    depot = _wheelhouse(s, cle)
    cible = git_url.strip() or package.strip()
    if git_url.strip():
        cible = "git+{}".format(git_url.strip())

    commandes = [
        "mkdir -p {}".format(shlex.quote(depot)),
        'echo "[romeo-mcp] construction de {} pour $(uname -m)"'.format(cible),
        "python -m pip wheel {} --no-deps --wheel-dir {} {}".format(
            shlex.quote(cible), shlex.quote(depot), build_flags
        ).strip(),
        "ls -la {}".format(shlex.quote(depot)),
    ]

    if not confirm:
        return {
            "ok": True, "submitted": False, "mode": "simulation",
            "arch": cle, "wheelhouse": depot, "commandes": commandes,
            "next_step": "Rappelle avec confirm=true pour lancer la construction.",
        }

    # La construction passe par build_on_node : c'est le seul chemin qui
    # garantit la bonne architecture.
    return build_on_node(
        commands=commandes,
        arch=cle,
        minutes=minutes,
        cpus=cpus_per_task,
        with_gpu=with_gpu,
        spack_packages=(spack_packages or []) + ["py-pip", "py-wheel", "py-setuptools"],
    )

@outil(
    annotations=MUTATING,
    description=(
        "Installe des paquets Python dans un environnement virtuel, sur un "
        "noeud de la bonne architecture, en privilegiant les roues deja "
        "compilees par build_wheel. Evite de recompiler les extensions natives "
        "et n'utilise jamais le noeud de login, dont les roues seraient en "
        "x86_64."
    ),
)
def romeo_pip_install(
    env_path: str,
    packages: list[str],
    arch: str = "armgpu",
    minutes: int = 30,
    extra_flags: str = "",
    confirm: bool = False,
) -> dict[str, Any]:
    """Installe dans un venv en s'appuyant sur le depot de roues local."""
    s = session()
    cle = arch.strip().lower()
    if cle not in ARCHS:
        return _error("architecture inconnue : {!r}.".format(arch))
    if not packages:
        return _error("aucun paquet a installer.")
    try:
        chemin = check_path(env_path, s.home, s.scratch, s.path_aliases)
    except GuardError as exc:
        return _error(str(exc))

    depot = _wheelhouse(s, cle)
    commandes = [
        "mkdir -p {}".format(shlex.quote(depot)),
        'if [ ! -f {}/bin/activate ]; then echo "environnement introuvable : {}" >&2; '
        "exit 1; fi".format(shlex.quote(chemin), chemin),
        ". {}/bin/activate".format(shlex.quote(chemin)),
        'echo "[romeo-mcp] installation dans {} sur $(uname -m)"'.format(chemin),
        "python -m pip install --find-links {} {} {}".format(
            shlex.quote(depot), extra_flags, " ".join(shlex.quote(p) for p in packages)
        ).strip(),
        "python -m pip list --format=columns | tail -n +3 | head -20",
    ]

    if not confirm:
        return {
            "ok": True, "submitted": False, "mode": "simulation",
            "arch": cle, "env": chemin, "wheelhouse": depot,
            "commandes": commandes,
            "next_step": "Rappelle avec confirm=true pour installer.",
        }

    return build_on_node(commands=commandes, arch=cle, minutes=minutes, cpus=16,
                         spack_packages=["py-pip"])

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

# =============================================================================
# Espace de travail distant
# =============================================================================
@outil(
    annotations=MUTATING,
    description=(
        "Ouvre un espace de travail interactif sur un noeud GPU et rend tout ce "
        "qu'il faut pour s'y connecter : commande de pont SSH a coller, et URL "
        "locale avec son jeton d'authentification. Contrairement a "
        "launch_interactive_service, le jeton est genere ici, donc l'URL est "
        "utilisable immediatement sans lire la sortie du job."
    ),
)
def spawn_remote_workspace(
    workspace_type: str = "jupyter",
    gpus: int = 1,
    time_limit: str = "2h",
    port: int = 8888,
    local_port: int = 0,
    cpus_per_task: int = 16,
    arch: str = "armgpu",
    workdir: str | None = None,
    spack_packages: list[str] | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Demarre un espace de travail authentifie et compose son acces local."""
    s = session()
    genre = (workspace_type or "jupyter").strip().lower()
    if genre not in ("jupyter", "code-server"):
        return _error(
            "type inconnu : {!r}. Valeurs : 'jupyter' ou 'code-server'.".format(
                workspace_type
            )
        )
    if genre == "code-server":
        return _error(
            "`code-server` n'est fourni ni par Spack ni par les modules de "
            "ROMEO : il faudrait installer soi-meme l'archive arm64 dans le "
            "scratch avant de pouvoir le lancer.",
            alternative=(
                "`jupyter` fonctionne immediatement. Pour du VS Code distant, "
                "l'extension Remote-SSH de ton editeur se connecte au noeud une "
                "fois l'allocation obtenue : vois allocate_debug_node."
            ),
        )

    port = int(port)
    if not (1024 <= port <= 65535):
        return _error("port hors plage utilisateur : {}".format(port))
    local_port = int(local_port) or port

    # Jeton genere ici : l'URL est ainsi complete des la reponse, sans avoir a
    # eplucher la sortie du job.
    jeton = secrets.token_urlsafe(24)
    commande = (
        "jupyter lab --no-browser --ip=0.0.0.0 --port={} "
        "--ServerApp.token={} --ServerApp.allow_origin='*'".format(port, jeton)
    )

    spec = JobSpec(
        name="mcp-workspace", command=commande, time=time_limit,
        gpus_per_node=max(0, int(gpus)), cpus_per_task=cpus_per_task, arch=arch,
        workdir=workdir, spack_packages=(spack_packages or []) + ["py-uv"],
    )
    try:
        if workdir:
            spec.workdir = check_path(workdir, s.home, s.scratch, s.path_aliases)
        plan = plan_job(spec, s.scratch)
    except (ClusterError, GuardError, SSHError, SSHTimeout) as exc:
        return _error(str(exc))

    if not confirm:
        return {
            "ok": True, "submitted": False, "mode": "simulation",
            "type": genre, "port_distant": port, "port_local": local_port,
            "script": plan.script,
            "note": (
                "JupyterLab doit exister dans l'environnement du noeud. La "
                "documentation ROMEO recommande `uv` : spack load py-uv, "
                "uv init, uv add jupyterlab."
            ),
            "next_step": "Rappelle avec confirm=true pour ouvrir l'espace.",
        }

    soumission = _soumettre_sbatch(
        s, plan, "mcp-workspace", note="espace de travail {}".format(genre)
    )
    if not soumission["ok"]:
        return soumission
    job_id = soumission["job_id"]

    noeud = _attendre_noeud(s, job_id, budget=240)
    reponse = {
        "ok": True, "submitted": True, "job_id": job_id, "type": genre,
        "node": noeud, "port_distant": port, "port_local": local_port,
        "workdir": plan.workdir,
    }
    if not noeud:
        reponse["next_step"] = (
            "Le noeud n'est pas encore affecte. Rappelle job_status('{}'), puis "
            "compose : ssh -N -L {}:<noeud>:{} {}".format(
                job_id, local_port, port, s.host)
        )
        return reponse

    reponse["tunnel"] = commande_tunnel(s.host, noeud, port, local_port)
    reponse["url"] = "http://localhost:{}/lab?token={}".format(local_port, jeton)
    reponse["next_step"] = (
        "Ouvre un terminal LOCAL, colle la commande `tunnel` et laisse-la "
        "tourner, puis ouvre `url`. Libere la reservation avec cancel_job('{}') "
        "quand tu as fini.".format(job_id)
    )
    return reponse
