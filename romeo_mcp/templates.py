"""Fragments de script generes pour les jobs ROMEO.

Le calcul parallele generique de ce cluster est **MPI** : la forme
documentee est un simple prefixe `srun`, sans variable de rendez-vous. Les
autres familles de lancement, les caches de bibliotheques Python et les
conteneurs relevent d'usages particuliers et sont donc **optionnels** :
rien ici ne s'active sans demande explicite.

Les specificites qui meritent d'etre encodees :

- le rendez-vous PyTorch (`MASTER_ADDR` derive du premier noeud alloue),
  sans lequel NCCL echoue tardivement et le diagnostic est penible ;
- les caches Python, qui saturent un home plafonne a 15 Go souples ;
- les conteneurs, qui doivent etre construits pour aarch64 sur la partie
  acceleree.
"""

from __future__ import annotations

#: Variables detournant les caches des bibliotheques Python hors du home.
_CACHES = (
    ("XDG_CACHE_HOME", ".cache"),
    ("HF_HOME", ".cache/huggingface"),
    ("HUGGINGFACE_HUB_CACHE", ".cache/huggingface/hub"),
    ("TRANSFORMERS_CACHE", ".cache/huggingface/transformers"),
    ("HF_DATASETS_CACHE", ".cache/huggingface/datasets"),
    ("TORCH_HOME", ".cache/torch"),
    ("TRITON_CACHE_DIR", ".cache/triton"),
    ("PIP_CACHE_DIR", ".cache/pip"),
    ("UV_CACHE_DIR", ".cache/uv"),
    ("MPLCONFIGDIR", ".cache/matplotlib"),
    ("WANDB_DIR", "wandb"),
    ("WANDB_CACHE_DIR", ".cache/wandb"),
)

#: `mpi` est la voie generique du calcul parallele sur ce cluster ; les
#: autres familles sont propres a l'ecosysteme PyTorch et n'ont de sens que
#: pour des charges de travail qui l'utilisent.
FAMILLES_DISTRIBUEES = ("mpi", "openmp", "ddp", "accelerate", "deepspeed", "srun")

#: Familles supposant des GPU et un point de rendez-vous PyTorch.
FAMILLES_PYTORCH = ("ddp", "accelerate", "deepspeed", "srun")

#: Les lanceurs qui deploient eux-memes un processus par GPU attendent une
#: seule tache SLURM par noeud ; les autres veulent une tache par GPU.
_UNE_TACHE_PAR_NOEUD = ("ddp", "accelerate")


def exports_caches(scratch: str) -> list[str]:
    """Redirige les caches des bibliotheques Python vers le scratch.

    Utile des qu'un job telecharge des modeles, des jeux de donnees ou des
    paquets : Hugging Face, PyTorch, pip, uv et matplotlib ecrivent tous
    sous `~/.cache` par defaut, et le home plafonne a 15 Go souples. Sans
    objet pour un code compile, d'ou une activation explicite."""
    base = "{}/caches".format(scratch.rstrip("/"))
    lignes = [
        "# Caches des bibliotheques Python deportes hors du home, dont le",
        "# quota souple de 15 Go serait sinon sature par un seul modele.",
    ]
    lignes += [
        'export {}="{}/{}"'.format(variable, base, suffixe)
        for variable, suffixe in _CACHES
    ]
    lignes.append(
        'mkdir -p "$XDG_CACHE_HOME" "$HF_HOME" "$TORCH_HOME" "$TRITON_CACHE_DIR" '
        '"$WANDB_DIR"'
    )
    return lignes


def attend_une_tache_par_noeud(famille: str) -> bool:
    return famille in _UNE_TACHE_PAR_NOEUD


def preambule_distribue(famille: str, gpus_par_noeud: int, nccl_debug: bool) -> list[str]:
    """Variables d'environnement du lancement parallele.

    Le MPI generique n'a besoin d'aucun point de rendez-vous : SLURM et
    OpenMPI se coordonnent seuls des lors que la commande passe par `srun`.
    Le rendez-vous MASTER_ADDR/MASTER_PORT est propre a PyTorch."""
    if famille in {"mpi", "openmp"}:
        return [
            "# SLURM et OpenMPI se coordonnent via srun : aucun point de",
            "# rendez-vous a declarer.",
            "export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-1}",
        ]
    lignes = [
        "# Point de rendez-vous : le premier noeud alloue fait office de maitre.",
        'export MASTER_ADDR="$(scontrol show hostnames "$SLURM_JOB_NODELIST" '
        '| head -n 1)"',
        "export MASTER_PORT=${MASTER_PORT:-29500}",
        'export GPUS_PER_NODE={}'.format(gpus_par_noeud),
        'export WORLD_SIZE=$(( SLURM_NNODES * GPUS_PER_NODE ))',
        "export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-1}",
    ]
    if famille in ("deepspeed", "srun"):
        lignes += [
            "# Un processus SLURM par GPU : les rangs viennent de SLURM.",
            'export RANK="$SLURM_PROCID"',
            'export LOCAL_RANK="$SLURM_LOCALID"',
            'export WORLD_SIZE="$SLURM_NTASKS"',
        ]
    if nccl_debug:
        lignes += ["export NCCL_DEBUG=INFO", "export NCCL_DEBUG_SUBSYS=INIT,COLL"]
    lignes.append('echo "[romeo-mcp] maitre=$MASTER_ADDR:$MASTER_PORT '
                  'monde=$WORLD_SIZE"')
    return lignes


def lanceur_distribue(famille: str, commande: str, gpus_par_noeud: int,
                      affinite: str = "") -> str:
    """Enveloppe la commande de l'utilisateur dans le lanceur adapte."""
    prefixe = "srun {} ".format(affinite) if affinite else "srun "
    if famille in {"mpi", "openmp"}:
        # Forme documentee par ROMEO : le simple prefixe srun suffit.
        return prefixe + commande
    if famille == "ddp":
        return (
            "srun torchrun \\\n"
            '  --nnodes="$SLURM_NNODES" \\\n'
            "  --nproc-per-node={} \\\n"
            '  --node-rank="$SLURM_NODEID" \\\n'
            "  --rdzv-backend=c10d \\\n"
            '  --rdzv-endpoint="$MASTER_ADDR:$MASTER_PORT" \\\n'
            "  {}".format(gpus_par_noeud, commande)
        )
    if famille == "accelerate":
        return (
            "srun accelerate launch \\\n"
            '  --num_machines="$SLURM_NNODES" \\\n'
            '  --num_processes="$WORLD_SIZE" \\\n'
            '  --machine_rank="$SLURM_NODEID" \\\n'
            '  --main_process_ip="$MASTER_ADDR" \\\n'
            '  --main_process_port="$MASTER_PORT" \\\n'
            "  {}".format(commande)
        )
    # deepspeed et srun : SLURM place lui-meme un processus par GPU.
    return prefixe + commande


def enveloppe_conteneur(image: str, commande: str, montages: list[str]) -> str:
    """Execute une commande dans un conteneur Apptainer, GPU compris.

    `--nv` expose les pilotes NVIDIA de l'hote ; sans lui le conteneur ne voit
    aucun GPU. Les espaces de travail doivent etre montes explicitement, faute
    de quoi le job ecrirait dans le systeme de fichiers ephemere de l'image.
    """
    options = ["exec", "--nv", "--cleanenv"]
    for montage in montages:
        options += ["--bind", montage]
    return "apptainer {} {} {}".format(" ".join(options), image, commande)


#: Services interactifs et leur ligne de lancement, port en parametre.
SERVICES = {
    "jupyter": {
        "libelle": "JupyterLab",
        "commande": "jupyter lab --no-browser --ip=0.0.0.0 --port={port}",
        "paquets": ["py-uv"],
        "note": "La documentation ROMEO recommande de creer l'environnement "
                "avec `uv` : `spack load py-uv`, `uv init`, `uv add jupyterlab`.",
    },
    "tensorboard": {
        "libelle": "TensorBoard",
        "commande": "tensorboard --logdir {logdir} --host 0.0.0.0 --port {port}",
        "paquets": [],
        "note": "Precise `logdir` avec le repertoire de tes journaux.",
    },
    "vllm": {
        "libelle": "serveur d'inference vLLM",
        "commande": "vllm serve {model} --host 0.0.0.0 --port {port}",
        "paquets": [],
        "note": "Demande au moins un GPU. Le modele est telecharge dans "
                "HF_HOME, redirige vers le scratch.",
    },
    "mlflow": {
        "libelle": "interface MLflow",
        "commande": "mlflow ui --host 0.0.0.0 --port {port}",
        "paquets": [],
        "note": "Sert l'interface de suivi d'experiences.",
    },
}


def commande_tunnel(hote_ssh: str, noeud: str, port_distant: int, port_local: int) -> str:
    """Commande de pont SSH, dans la forme documentee par ROMEO."""
    return "ssh -N -L {}:{}:{} {}".format(port_local, noeud, port_distant, hote_ssh)


#: Capacite reelle de /dev/shm sur un noeud, relevee le 2026-08-20.
SHM_TOTAL_GO = 239


def preambule_nettoyage() -> list[str]:
    """Installe une file de nettoyage unique, executee a la sortie du job.

    Bash n'accepte qu'un seul piege `EXIT` : deux `trap ... EXIT` successifs
    s'ecrasent silencieusement. Les differents preambules empilent donc leurs
    actions dans un tableau, qu'un unique piege deroule.
    """
    return [
        "# Bash n'admet qu'un seul piege EXIT : on empile les nettoyages dans",
        "# une file que ce piege unique deroule.",
        "_ROMEO_NETTOYAGE=()",
        "_romeo_nettoyer() {",
        '  local action',
        '  for action in "${_ROMEO_NETTOYAGE[@]}"; do eval "$action" || true; done',
        "}",
        "trap _romeo_nettoyer EXIT",
    ]


def preambule_staging_shm(archive: str, variable: str = "DATASET_DIR") -> list[str]:
    """Deballe un jeu de donnees en memoire vive avant le calcul.

    Lire des milliers de petits fichiers depuis GPFS effondre le debit ; les
    relire depuis un tmpfs local le restaure. Deux limites reelles, souvent
    ignorees : `/dev/shm` fait 239 Go et non la taille de la RAM du noeud, et
    il est **partage entre les jobs du meme noeud**. Sa consommation etant
    imputee au cgroup memoire du job, `--mem` doit couvrir la taille
    decompressee.
    """
    return [
        "# Jeu de donnees mis en cache en memoire vive : /dev/shm est un tmpfs",
        "# de {} Go partage entre les jobs du noeud, et sa consommation compte".format(
            SHM_TOTAL_GO
        ),
        "# dans la memoire du job. --mem doit couvrir la taille decompressee.",
        'STAGE_DIR="/dev/shm/$SLURM_JOB_ID"',
        'mkdir -p "$STAGE_DIR"',
        "_ROMEO_NETTOYAGE+=('rm -rf \"$STAGE_DIR\"')",
        'echo "[romeo-mcp] extraction de {} vers $STAGE_DIR"'.format(archive),
        'tar -xf "{}" -C "$STAGE_DIR"'.format(archive),
        'export {}="$STAGE_DIR"'.format(variable),
        'echo "[romeo-mcp] donnees pretes : $(du -sh "$STAGE_DIR" | cut -f1) '
        'en memoire, ${} pointe dessus"'.format("{" + variable + "}"),
    ]


#: Extensions rapatriees avant destruction du repertoire temporaire.
RESULTATS_PAR_DEFAUT = ("*.log", "*.out", "*.chk", "*.dat", "*.csv", "*.h5")


def preambule_tmpdir(scratch: str, conserver: list[str] | None = None) -> list[str]:
    """Isole les fichiers temporaires du job et garantit leur suppression.

    Les codes de chimie quantique ou de structure electronique ecrivent des
    fichiers d'integrales enormes (`.rwf`, `.scr`) qui saturent un quota de
    20 Go, et laissent derriere eux des millions de petits fichiers qui
    alourdissent les metadonnees GPFS. On leur donne un repertoire propre au
    job, designe par `$TMPDIR` que respectent la plupart des codes, et on le
    detruit a la sortie **apres avoir rapatrie les resultats**.
    """
    motifs = list(conserver or RESULTATS_PAR_DEFAUT)
    return [
        "# Repertoire temporaire propre au job : les gros fichiers de travail y",
        "# vivent et disparaissent a la fin, sans laisser de residus.",
        'export TMPDIR="{}/job_$SLURM_JOB_ID"'.format(scratch.rstrip("/")),
        'mkdir -p "$TMPDIR"',
        "_romeo_rapatrier() {",
        '  # Les resultats sont sauves AVANT la destruction du temporaire.',
        '  local destination="${SLURM_SUBMIT_DIR:-$PWD}" fichier echec=0',
        "  shopt -s nullglob",
        '  for fichier in {}; do'.format(
            " ".join('"$TMPDIR"/{}'.format(m) for m in motifs)
        ),
        '    cp -a "$fichier" "$destination"/ || echec=1',
        "  done",
        "  shopt -u nullglob",
        '  if [ "$echec" -eq 0 ]; then rm -rf "$TMPDIR"; else',
        '    echo "[romeo-mcp] copie echouee : TMPDIR conserve dans $TMPDIR" >&2',
        '  fi',
        "}",
        "_ROMEO_NETTOYAGE+=('_romeo_rapatrier')",
        'echo "[romeo-mcp] TMPDIR=$TMPDIR (detruit en fin de job, {} conserves)"'.format(
            ", ".join(motifs)
        ),
    ]


def options_affinite(cpus_par_tache: int, mode: str | None = None) -> str:
    """Options de placement pour un lancement hybride MPI + OpenMP.

    Sans liaison explicite, les fils OpenMP de rangs voisins se disputent les
    memes coeurs et le gain du parallelisme hybride disparait. Les noeuds de
    ROMEO etant tres denses (192 a 288 coeurs), l'effet est marque.
    """
    if mode:
        return "--cpu-bind={}".format(mode)
    return "--cpu-bind=cores" if cpus_par_tache > 1 else ""


def enveloppe_resiliente(
    commande: str, checkpoint_dir: str, preavis: int
) -> list[str]:
    """Rend la commande interruptible et reprenable.

    SLURM previent par `SIGUSR1` un peu avant l'expiration du temps alloue.
    Le script relaie ce signal a l'application et depose un temoin, ce qui lui
    laisse le temps d'ecrire un point de reprise propre. Un marqueur `TERMINE`
    permet aux segments suivants de la chaine de s'effacer quand le calcul est
    fini avant terme.
    """
    return [
        'CHECKPOINT_DIR="{}"'.format(checkpoint_dir),
        'mkdir -p "$CHECKPOINT_DIR"',
        'if [ -f "$CHECKPOINT_DIR/TERMINE" ]; then',
        '  echo "[romeo-mcp] segment ignore : calcul deja marque termine"',
        "  exit 0",
        "fi",
        "",
        "# SLURM envoie SIGUSR1 {} s avant la fin du temps alloue.".format(preavis),
        "_sauvegarde_demandee() {",
        '  echo "[romeo-mcp] SIGUSR1 : {} s avant la fin, sauvegarde demandee"'.format(
            preavis
        ),
        '  touch "$CHECKPOINT_DIR/SAUVEGARDE_DEMANDEE"',
        '  if [ -n "${APP_PID:-}" ]; then kill -USR1 "$APP_PID" 2>/dev/null || true; fi',
        "}",
        "trap _sauvegarde_demandee SIGUSR1",
        "",
        "# L'application tourne en arriere-plan pour que le shell reste capable",
        "# de recevoir le signal pendant son execution. Elle est enveloppee dans",
        "# une fonction : mettre directement `commande &` en arriere-plan ne",
        "# lancerait que sa DERNIERE ligne si elle en compte plusieurs, et",
        "# APP_PID designerait alors le mauvais processus : la sauvegarde sur",
        "# SIGUSR1 ne serait jamais demandee.",
        "_romeo_charge() {",
        commande,
        "}",
        "_romeo_charge &",
        "APP_PID=$!",
        "set +e",
        'wait "$APP_PID"; CODE=$?',
        "# `wait` rend la main des qu'un signal est traite : on repart en attente",
        "# tant que l'application vit encore.",
        'while [ "$CODE" -gt 128 ] && kill -0 "$APP_PID" 2>/dev/null; do',
        '  wait "$APP_PID"; CODE=$?',
        "done",
        "set -e",
        'echo "[romeo-mcp] code de sortie applicatif : $CODE"',
        'if [ "$CODE" -eq 0 ]; then',
        '  touch "$CHECKPOINT_DIR/TERMINE"',
        '  echo "[romeo-mcp] calcul termine : les segments suivants seront ignores"',
        "fi",
        'echo "[romeo-mcp] fin $(date -Is)"',
        'exit "$CODE"',
    ]
