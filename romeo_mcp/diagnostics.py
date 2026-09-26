"""Analyse post-mortem des jobs echoues.

Un modele confronte a un job en echec enchaine sinon les allers-retours :
`sacct` pour l'etat, lecture du `.err`, recherche du code d'erreur, relecture
du script. Ce module condense cette enquete en une passe : il reconnait les
modes d'echec classiques d'un cluster, et surtout ceux propres a ROMEO, ou la
premiere cause d'echec silencieux reste l'architecture.

Chaque cause porte son remede sous forme d'actions concretes, exprimees dans le
vocabulaire des outils du serveur.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Cause:
    """Un mode d'echec reconnu, avec son explication et ses remedes."""

    cle: str
    libelle: str
    explication: str
    remedes: list[str] = field(default_factory=list)
    #: Extrait du journal ayant declenche la detection.
    preuve: str = ""


#: Motifs recherches dans les sorties du job. L'ordre compte : les causes les
#: plus specifiques passent avant les plus generiques, car une seule suffit
#: souvent a expliquer la cascade d'erreurs qui suit.
_MOTIFS: list[tuple[str, Cause]] = [
    (
        r"Illegal instruction|SIGILL|Exec format error|cannot execute binary file"
        r"|wrong ELF class|is not a valid ELF",
        Cause(
            "architecture",
            "binaire incompatible avec l'architecture du noeud",
            "Le programme a ete compile pour une architecture differente de "
            "celle du noeud d'execution. Sur ROMEO, c'est le piege numero un : "
            "le noeud de login est en x86_64 alors que les noeuds GPU sont en "
            "aarch64, donc tout artefact produit sur le login y est inutilisable.",
            [
                "Recompile ou reinstalle sur la bonne famille de noeuds avec "
                "`build_on_node(arch='armgpu', ...)`.",
                "Pour un environnement Python, recree-le depuis un noeud de "
                "calcul : les roues telechargees sur le login sont en x86_64.",
                "Verifie l'architecture attendue avec `uname -m` dans le job.",
            ],
        ),
    ),
    (
        r"no kernel image is available for execution|CUDA error: no kernel image",
        Cause(
            "capacite_cuda",
            "binaire CUDA compile pour une autre capacite de calcul",
            "Le code CUDA n'embarque pas de noyau pour l'architecture du GPU. "
            "Les GH200 de ROMEO sont en capacite de calcul sm_90.",
            [
                "Recompile avec `-arch=sm_90` (ou `TORCH_CUDA_ARCH_LIST=9.0`).",
                "Pour PyTorch, installe une roue compatible CUDA 12.x pour "
                "aarch64 : voir la page `utiliser_python` de la documentation.",
            ],
        ),
    ),
    (
        r"CUDA out of memory|torch\.cuda\.OutOfMemoryError"
        r"|cudaErrorMemoryAllocation|CUBLAS_STATUS_ALLOC_FAILED",
        Cause(
            "memoire_gpu",
            "memoire du GPU saturee",
            "La VRAM du GPU est pleine. Chaque GH200 offre environ 96 Gio, ce "
            "qui est confortable : une saturation vient plus souvent d'un lot "
            "trop grand ou d'une fuite que d'un manque reel.",
            [
                "Reduis la taille de lot, ou compense par de l'accumulation de "
                "gradient pour conserver le lot effectif.",
                "Active la precision mixte (bf16 est bien supporte sur Hopper) "
                "et le `gradient checkpointing`.",
                "Repartis sur plusieurs GPU : `submit_job(gpus_per_node=4, "
                "distributed='ddp')`.",
                "Contre la fragmentation : "
                "`PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`.",
            ],
        ),
    ),
    (
        r"oom[-_ ]?kill|Out Of Memory|OOMKilled|exceeded memory limit"
        r"|Detected \d+ oom[-_ ]?kill|slurmstepd: error: Exceeded job memory",
        Cause(
            "memoire_vive",
            "job tue faute de memoire vive",
            "Le job a depasse la memoire demandee et a ete tue. Sur ROMEO "
            "`--mem` est obligatoire, donc la valeur utilisee est celle que tu "
            "as demandee ou celle derivee de tes coeurs.",
            [
                "Consulte `job_efficiency` : il donne la RSS maximale reellement "
                "atteinte, base fiable pour recalibrer.",
                "Augmente `mem_gb` a environ 1,3 fois ce pic.",
                "Si le pic vient du chargement de donnees, reduis le nombre de "
                "processus de chargement.",
            ],
        ),
    ),
    (
        r"Bus error|SIGBUS",
        Cause(
            "memoire_partagee",
            "erreur de bus, typiquement la memoire partagee",
            "Un acces memoire invalide, le plus souvent un depassement de "
            "`/dev/shm` : les DataLoader PyTorch y stockent les tenseurs "
            "echanges entre processus. Le noeud expose 239 Go de `/dev/shm`, "
            "mais le cgroup du job plafonne l'usage a la memoire demandee.",
            [
                "Augmente `mem_gb` : c'est ce plafond qui limite `/dev/shm`.",
                "Reduis `num_workers` du DataLoader, ou passe la strategie de "
                "partage a `file_system`.",
            ],
        ),
    ),
    (
        r"NCCL (error|WARN)|ncclUnhandledCudaError|ncclSystemError"
        r"|ncclInternalError|Connection refused.*MASTER|Timed out initializing",
        Cause(
            "communication_gpu",
            "echec de communication entre GPU ou entre noeuds",
            "NCCL n'a pas pu etablir ou maintenir les communications "
            "collectives. En multi-noeuds, la cause habituelle est un point de "
            "rendez-vous mal renseigne ou un lancement sans `srun`.",
            [
                "Relance avec `distributed='ddp'` : le serveur genere "
                "`MASTER_ADDR`, `MASTER_PORT` et le lancement via `srun`.",
                "Ajoute `NCCL_DEBUG=INFO` pour obtenir la cause exacte.",
                "Verifie que le nombre de processus correspond bien aux GPU "
                "alloues.",
            ],
        ),
    ),
    (
        r"Disk quota exceeded|No space left on device|quota exceeded",
        Cause(
            "quota",
            "quota de stockage atteint",
            "L'ecriture a ete refusee faute d'espace. Home et scratch partagent "
            "le meme plafond de 15 Go souple et 20 Go strict, et le depassement "
            "du quota souple n'ouvre qu'un delai de grace de 7 jours.",
            [
                "Verifie l'etat exact avec `romeo_quota`.",
                "Fais le menage avec `storage_cleanup_helper`.",
                "Redirige les caches des bibliotheques IA hors du home : "
                "`submit_job(redirect_caches=True)` s'en charge.",
            ],
        ),
    ),
    (
        r"ModuleNotFoundError: No module named ['\"]?([\w.]+)",
        Cause(
            "module_python",
            "module Python introuvable",
            "L'interpreteur ne trouve pas un paquet. Sur ROMEO, un job n'herite "
            "d'aucun environnement par defaut : sans chargement explicite, "
            "meme `spack` est absent.",
            [
                "Passe les paquets voulus en `spack_packages` a `submit_job`.",
                "Si tu utilises un environnement virtuel, active-le dans la "
                "commande du job.",
                "Verifie que l'environnement a ete cree sur la meme "
                "architecture que le noeud d'execution.",
            ],
        ),
    ),
    (
        r"error while loading shared libraries|cannot open shared object file"
        r"|undefined symbol",
        Cause(
            "bibliotheque",
            "bibliotheque partagee introuvable",
            "L'editeur de liens dynamique ne trouve pas une bibliotheque, ou "
            "en trouve une incompatible.",
            [
                "Charge le paquet fournissant la bibliotheque via "
                "`spack_packages`.",
                "Cherche-le avec `romeo_software`.",
                "Assure-toi que le chargement se fait sur la meme architecture "
                "que la compilation.",
            ],
        ),
    ),
    (
        r"Permission denied",
        Cause(
            "permission",
            "acces refuse",
            "Le job n'a pas les droits sur un fichier ou un repertoire.",
            [
                "Verifie le chemin avec `list_dir`.",
                "Ecris dans `/scratch_p/$USER` ou `/project/<code>` ; `/apps` "
                "est en lecture seule.",
            ],
        ),
    ),
]

#: Etats SLURM qui portent a eux seuls l'explication de l'echec.
_ETATS: dict[str, Cause] = {
    "TIMEOUT": Cause(
        "temps",
        "limite de temps atteinte",
        "SLURM a interrompu le job a l'expiration de `--time`. Le calcul "
        "n'a pas echoue en soi : il n'a pas eu le temps de finir.",
        [
            "Augmente `time_limit` ; la partition sera deduite automatiquement.",
            "Au-dela d'un jour, seule la partition `long` convient.",
            "Mieux : reprends depuis un point de sauvegarde. `diagnose_job` "
            "signale les points de reprise trouves dans le repertoire du job.",
        ],
    ),
    "OUT_OF_MEMORY": Cause(
        "memoire_vive",
        "job tue faute de memoire vive",
        "SLURM a tue le job pour depassement de la memoire demandee.",
        [
            "Consulte `job_efficiency` pour la RSS maximale atteinte.",
            "Augmente `mem_gb` a environ 1,3 fois ce pic.",
        ],
    ),
    "NODE_FAIL": Cause(
        "noeud",
        "defaillance materielle du noeud",
        "Le noeud alloue est tombe. L'echec n'est pas imputable au calcul.",
        ["Resoumets tel quel.", "Si cela se repete, signale-le a l'equipe ROMEO."],
    ),
    "CANCELLED": Cause(
        "annulation",
        "job annule",
        "Le job a ete annule, par toi-meme ou par un administrateur.",
        ["Verifie qu'il ne s'agit pas d'un depassement de limite du compte."],
    ),
}

# --- codes de sortie -------------------------------------------------------
#: Signaux POSIX courants et ce qu'ils revelent sur un cluster.
_SIGNAUX: dict[int, tuple[str, str, list[str]]] = {
    2: ("SIGINT", "interruption demandee", ["Relance si l'arret etait involontaire."]),
    6: ("SIGABRT", "abandon du programme, souvent une assertion ou un abort()",
        ["Cherche le message d'assertion dans la sortie d'erreur.",
         "Une bibliotheque mal appariee produit aussi ce signal."]),
    8: ("SIGFPE", "exception arithmetique, division par zero ou depassement",
        ["Verifie les donnees d'entree : une valeur nulle ou aberrante suffit."]),
    9: ("SIGKILL", "processus tue sans possibilite de se defendre",
        ["Cause la plus frequente : le tueur de memoire du noyau. "
         "Recoupe avec `job_efficiency` pour voir la RSS atteinte.",
         "Sinon : annulation forcee, ou depassement du temps alloue."]),
    11: ("SIGSEGV", "violation d'acces memoire",
         ["Pointeur invalide, indice hors bornes, ou pile debordee.",
          "Une pile trop petite se corrige par `ulimit -s unlimited` dans le job.",
          "Si le binaire vient d'une autre architecture, l'erreur peut n'etre "
          "qu'un symptome : verifie `uname -m`."]),
    15: ("SIGTERM", "arret demande proprement",
         ["Sur un cluster, c'est presque toujours la fin du temps alloue.",
          "Augmente `time_limit`, ou passe par `submit_resilient_job` pour "
          "reprendre depuis un point de sauvegarde."]),
}

#: Codes de sortie du shell qui ont un sens propre, hors signaux.
_CODES_SHELL: dict[int, tuple[str, list[str]]] = {
    1: ("erreur generique du programme",
        ["Le code a echoue de lui-meme : la cause est dans sa sortie."]),
    2: ("mauvais usage d'une commande shell",
        ["Souvent une option inconnue ou un argument manquant."]),
    126: ("fichier trouve mais non executable",
          ["Ajoute le droit d'execution : `chmod +x <fichier>`.",
           "Verifie aussi que le systeme de fichiers n'est pas monte en noexec."]),
    127: ("commande ou binaire introuvable",
          ["Sur ROMEO, un job n'herite d'aucun environnement : sans "
           "`romeo_load_<arch>_env` puis `spack load`, meme les outils "
           "courants sont absents.",
           "Verifie le `$PATH` effectif et l'orthographe de la commande.",
           "Un script avec des fins de ligne Windows produit aussi ce code : "
           "verifie-le avec `sbatch_lint`."]),
}


def decoder_code_sortie(exit_code: str, derived: str = "") -> dict | None:
    """Traduit le couple `code:signal` de sacct.

    SLURM note le code sous la forme `<code>:<signal>`. Un processus tue par
    signal apparait donc soit en `0:9`, soit en `137:0` quand c'est le shell
    qui rapporte la convention 128+n. Les deux formes sont traitees.
    """
    texte = (exit_code or "").strip()
    if not texte:
        return None

    code, _, signal = texte.partition(":")
    try:
        code = int(code)
        signal = int(signal) if signal else 0
    except ValueError:
        return None

    # Le signal explicite prime ; sinon on decode la convention 128+n.
    numero = signal or (code - 128 if code > 128 else 0)
    if numero and numero in _SIGNAUX:
        nom, libelle, remedes = _SIGNAUX[numero]
        return {
            "code": texte, "signal": numero, "nom": nom,
            "libelle": "{} : {}".format(nom, libelle), "remedes": remedes,
        }
    if numero:
        return {
            "code": texte, "signal": numero, "nom": "signal {}".format(numero),
            "libelle": "processus arrete par le signal {}".format(numero),
            "remedes": ["Consulte `man 7 signal` pour la signification exacte."],
        }
    if code in _CODES_SHELL:
        libelle, remedes = _CODES_SHELL[code]
        return {
            "code": texte, "signal": 0, "nom": "code {}".format(code),
            "libelle": libelle, "remedes": remedes,
        }
    if code:
        return {
            "code": texte, "signal": 0, "nom": "code {}".format(code),
            "libelle": "le programme s'est termine avec le code {}".format(code),
            "remedes": ["Ce code vient du programme : sa signification lui est "
                        "propre, cherche-la dans sa documentation."],
        }
    return None


#: Fichiers ressemblant a des points de reprise, pour proposer une relance.
_MOTIFS_CHECKPOINT = (
    "*.ckpt", "*.pt", "*.pth", "*.safetensors",
    "checkpoint*", "*checkpoint*/", "last*", "*.h5",
)


def analyser(
    etat: str,
    code_sortie: str,
    journal: str,
    limites: dict | None = None,
    code_derive: str = "",
) -> dict:
    """Diagnostique un job a partir de son etat et de ses sorties.

    ``journal`` reunit la fin des flux d'erreur et de sortie standard.
    """
    causes: list[Cause] = []
    vues: set[str] = set()

    etat_court = (etat or "").split()[0].upper() if etat else ""
    if etat_court in _ETATS:
        cause = _ETATS[etat_court]
        causes.append(cause)
        vues.add(cause.cle)

    for motif, modele in _MOTIFS:
        correspondance = re.search(motif, journal or "", re.IGNORECASE)
        if not correspondance or modele.cle in vues:
            continue
        debut = max(0, correspondance.start() - 90)
        extrait = (journal[debut : correspondance.end() + 160]).strip()
        causes.append(
            Cause(
                modele.cle,
                modele.libelle,
                modele.explication,
                list(modele.remedes),
                preuve=extrait,
            )
        )
        vues.add(modele.cle)

    # Le code de sortie explique souvent a lui seul l'echec, meme quand aucun
    # motif n'apparait dans le journal : un binaire tue par SIGKILL n'a pas
    # forcement eu le temps d'ecrire quoi que ce soit.
    decodage = decoder_code_sortie(code_sortie, code_derive)
    if decodage and decodage["signal"] and decodage["nom"] not in ("SIGTERM",):
        cle = "signal_{}".format(decodage["signal"])
        if cle not in vues:
            causes.append(
                Cause(cle, decodage["libelle"],
                      "Le processus a ete arrete par un signal plutot que de se "
                      "terminer normalement.", list(decodage["remedes"]),
                      preuve="ExitCode {}".format(decodage["code"]))
            )
            vues.add(cle)
    elif decodage and not decodage["signal"] and decodage["code"] not in ("0:0", "0"):
        cle = "code_sortie"
        if cle not in vues:
            causes.append(
                Cause(cle, decodage["libelle"],
                      "Le programme s'est termine de lui-meme avec ce code.",
                      list(decodage["remedes"]),
                      preuve="ExitCode {}".format(decodage["code"]))
            )
            vues.add(cle)

    resultat = {
        "etat": etat,
        "exit_code": code_sortie,
        "code_decode": decodage,
        "causes": [
            {
                "cle": c.cle,
                "libelle": c.libelle,
                "explication": c.explication,
                "remedes": c.remedes,
                "preuve": c.preuve,
            }
            for c in causes
        ],
    }

    if not causes:
        indice = "aucun motif d'echec connu reconnu"
        if code_sortie and code_sortie not in ("0:0", "0"):
            indice += " ; le code de sortie {} vient du programme lui-meme".format(
                code_sortie
            )
        resultat["causes"] = []
        resultat["indice"] = (
            indice + ". Relis la sortie complete avec `job_output(stream='both')`."
        )

    if limites:
        resultat["limites"] = limites
    return resultat


def commande_recherche_checkpoints(workdir: str) -> str:
    """Commande shell listant les points de reprise plausibles d'un job."""
    motifs = " -o ".join('-name "{}"'.format(m.rstrip("/")) for m in _MOTIFS_CHECKPOINT)
    return (
        "find {} -maxdepth 3 \\( {} \\) -printf '%T@ %p %s\\n' 2>/dev/null "
        "| sort -rn | head -8".format(workdir, motifs)
    )
