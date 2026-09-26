"""Socle partage : objet serveur, enregistrement des outils, appuis communs.

Ce module ne declare **aucun** outil. Il porte ce dont tous ont besoin : le
serveur MCP, le decorateur qui garantit qu'un outil ne leve jamais, et les
fonctions d'appui partagees entre plusieurs familles d'outils.

Le separer evite l'alternative qui a fait grossir `server.py` jusqu'a 4700
lignes : soit tout mettre dans un fichier, soit laisser chaque module d'outils
dependre de tous les autres.
"""

from __future__ import annotations

import functools
import inspect
import os
import posixpath
import re
import shlex
import time
from pathlib import Path
from .profiles import ProfiledServer
from mcp.types import ToolAnnotations
from .cluster import ARCHS, ClusterError, parse_duration
from .guard import GuardError
from .registry import registry
from .ssh import SSHError, SSHTimeout, session
from . import __version__


"""Serveur MCP pour le supercalculateur ROMEO (URCA).

Principe de conception : ne pas exposer un shell. Chaque outil encode une
intention de haut niveau, valide les contraintes du cluster avant d'agir, et
rend une sortie compacte. Les erreurs frequentes d'un modele sur un cluster
(mauvaise partition, mauvaise architecture, calcul sur le noeud de login, log
de 200 Mo injecte dans le contexte) sont rendues structurellement difficiles.
"""

INSTRUCTIONS = """\
Acces au supercalculateur ROMEO (URCA), ordonnance par SLURM.

A savoir avant toute action :

- Le profil essential presente les outils courants. Si un outil avance manque
  au catalogue, appelle `tool_profile` avec profile="full", puis relis tools/list.
- Le noeud de login est en x86_64, les noeuds GPU sont en aarch64. Ne compile
  et n'installe jamais depuis le login : passe par `build_on_node`.
- Les logiciels se chargent via Spack, propre a chaque architecture. Cherche-les
  avec `romeo_software`, puis passe-les en `spack_packages`. Ne conclus jamais
  qu'un outil est absent parce que `command -v` ne le trouve pas sur le login.
- Aucun calcul sur le noeud de login. Tout passe par `submit_job`.
- ROMEO est un calculateur generaliste : chimie, mecanique des fluides,
  bio-informatique, statistique, apprentissage automatique. Le parallelisme
  courant est MPI (`distributed='mpi'`, simple prefixe srun). Les options
  propres a PyTorch, aux conteneurs ou aux caches Python sont facultatives et
  desactivees par defaut : ne les active que si la charge de travail les
  concerne reellement.
- `submit_job` fonctionne en simulation par defaut : il rend le script sbatch
  genere et les avertissements. Relance avec `confirm=true` pour soumettre.
- Les partitions sont `instant` (1 h), `short` (1 jour) et `long` (30 jours).
  Ne precise pas la partition : elle est deduite du temps demande.
- Apres un job, lis `job_efficiency` : il remplace `seff` (absent) et indique
  comment recalibrer le dimensionnement au run suivant.
- Commence par lire la ressource `romeo://cheatsheet` en cas de doute.
- La documentation officielle du cluster est disponible hors ligne : interroge-la
  avec `search_docs` (mots-cles ou question) avant une commande incertaine.
  Les resultats donnent titres, source et lignes. Lis `read_args` avec `read_doc`,
  puis suis `next_call` si la reponse est tronquee. Le corpus est date : les
  quotas et l'etat courant du cluster doivent etre verifies avec les outils.
"""

server = ProfiledServer(
    name="romeo",
    title="ROMEO (URCA)",
    version=__version__,
    instructions=INSTRUCTIONS,
)

READ_ONLY = ToolAnnotations(read_only_hint=True)

MUTATING = ToolAnnotations(read_only_hint=False, destructive_hint=False)

def outil(**options):
    """Enregistre un outil MCP en garantissant qu'il ne leve jamais.

    Un outil qui laisse echapper une exception fait remonter au modele une
    trace de pile Python au lieu d'une erreur exploitable, et lui retire tout
    moyen de se corriger. Chaque outil attrape deja ses erreurs attendues ;
    cette enveloppe est le filet pour celles qu'on n'a pas prevues.

    `functools.wraps` conserve `__wrapped__`, dont `inspect.signature` se sert :
    le schema expose par MCP reste donc celui de la fonction d'origine, avec
    ses parametres et leurs valeurs par defaut.
    """
    def decorateur(fonction):
        @functools.wraps(fonction)
        def enveloppe(*args, **kwargs):
            try:
                return fonction(*args, **kwargs)
            except (SSHError, SSHTimeout, ClusterError, GuardError) as exc:
                # Erreurs du domaine : leur message est deja redige pour le
                # modele, inutile de le maquiller.
                return _error(str(exc))
            except Exception as exc:  # noqa: BLE001 - dernier rempart volontaire
                return _error(
                    "erreur inattendue dans {} : {}: {}".format(
                        fonction.__name__, type(exc).__name__, exc
                    ),
                    inattendu=True,
                )
        if inspect.iscoroutinefunction(fonction):
            @functools.wraps(fonction)
            async def enveloppe(*args, **kwargs):
                try:
                    return await fonction(*args, **kwargs)
                except (SSHError, SSHTimeout, ClusterError, GuardError, ValueError) as exc:
                    return _error(str(exc))
                except Exception as exc:
                    return _error("erreur inattendue dans {} : {}".format(
                        fonction.__name__, type(exc).__name__), inattendu=True)
        # `structured_output` fait remplir `structuredContent` cote client :
        # sans lui, mcp 2.0 ne rend que du JSON dans du texte, que chaque
        # client doit reparser. Le schema derive de `dict[str, Any]` ne promet
        # rien de plus que « un objet » -- c'est exact, et c'est deja ce que
        # les outils garantissent : une enveloppe libre autour de `ok`.
        options.setdefault("structured_output", True)
        return server.tool(**options)(enveloppe)
    return decorateur

#: Plafond dur d'attente synchrone : un appel d'outil ne doit jamais sequestrer
#: le modele pendant des heures.
MAX_WAIT_SECONDS = 600

MAX_BUILD_SECONDS = 900

#: Plafonds d'analyse de `sbatch_lint`. Ils bornent le cout d'un appel,
#: jamais la verite de son verdict : des qu'ils mordent, l'outil dit
#: combien d'elements il a laisses de cote.
#: Nom d'un enchainement : il sert de repertoire et de prefixe aux jobs.
_NOM_ENCHAINEMENT = re.compile(r"^[A-Za-z0-9._-]{1,48}$")

MAX_CHEMINS_VERIFIES = 20

MAX_VARIABLES_SIGNALEES = 8

#: Au-dela de ce delai, une commande est consideree comme longue et bascule sur
#: la seconde session SSH. Le seuil separe l'inspection (quelques secondes) des
#: travaux qui monopolisent le transport : compiler, profiler, installer.
SEUIL_SESSION_LONGUE = 120

def _sh(session_obj, command: str, **kwargs):
    """Execute une commande distante, sur la session adaptee a sa duree.

    Le choix est fait ici plutot qu'a chaque appel : c'est l'unique point de
    passage vers le transport, et le delai demande dit deja tout ce qu'il faut
    savoir pour trancher.
    """
    if kwargs.get("timeout", 30) >= SEUIL_SESSION_LONGUE:
        session_obj = session(longue=True)
    return session_obj.run(command, **kwargs)

#: Fenetre pendant laquelle une soumission identique est consideree comme un
#: doublon probable. Assez large pour couvrir une reprise apres erreur reseau
#: ou une relance de modele, assez courte pour ne pas gener une repetition
#: voulue -- relancer le meme calcul une heure plus tard reste legitime.
FENETRE_DOUBLON_SECONDES = 900

#: Etats SLURM dans lesquels un job precedent rend un doublon reellement
#: genant : il occupe deja la file ou tourne.
ETATS_ACTIFS = {"PENDING", "RUNNING", "CONFIGURING", "SUSPENDED", "soumis"}

def _doublon_recent(script: str) -> dict | None:
    """Job identique soumis il y a peu et toujours actif, s'il en existe un.

    Un modele qui n'obtient pas de reponse claire reessaie -- c'est son
    comportement normal, pas une anomalie. Sans garde, la deuxieme tentative
    double la facture et la file. Le registre conserve deja le script soumis :
    le comparer coute une lecture locale.
    """
    limite = time.time() - FENETRE_DOUBLON_SECONDES
    for entree in registry().recent(limit=20):
        if entree.get("submitted_at", 0) < limite:
            break  # le registre est trie par date decroissante
        if entree.get("script") != script:
            continue
        if (entree.get("last_state") or "soumis") in ETATS_ACTIFS:
            return entree
    return None

def _controle_du_script_genere(script: str) -> list[str]:
    """Passe le script genere par le serveur dans son propre linter.

    Le serveur produisait un script puis l'envoyait sans jamais le relire avec
    l'outil qu'il expose pour cela. Une regression de gabarit -- une directive
    `#SBATCH` glissee apres la premiere commande, un `--mem` perdu -- ne serait
    apparue qu'a la soumission, sous la forme d'un refus opaque de SLURM.
    """
    # Import tardif volontaire : le noyau ne doit dependre d'aucun module
    # d'outils, sous peine de cycle. C'est le seul appel du noyau vers le
    # haut, et il est confine a cette fonction.
    from .outils_donnees import sbatch_lint

    try:
        rapport = sbatch_lint(script=script)
    except Exception:  # noqa: BLE001 - un auto-controle ne doit jamais bloquer
        return []
    return [
        "auto-controle du script genere : {}".format(c["message"])
        for c in rapport.get("constats", [])
        if c.get("gravite") == "haute"
    ]

def _contexte_chemins(session_obj, confirm: bool) -> tuple[str, str, list[str], str]:
    """Racines de chemins pour la planification, utilisables hors ligne.

    La simulation est le mode le plus utile du serveur -- verifier un
    dimensionnement *avant* de soumettre -- et c'etait paradoxalement le plus
    contraint : il ouvrait une session SSH pour la seule raison de connaitre le
    scratch. Une simulation doit pouvoir tourner depuis un portable dans le
    train, et la suite de tests doit pouvoir l'exercer sans cluster.

    `ROMEO_SCRATCH` (et `ROMEO_HOME`) figent les racines sans aller-retour. A
    defaut on interroge la session ; si elle est injoignable, on ne se rabat sur
    des valeurs illustratives **que** pour une simulation. Une soumission reelle
    remonte l'erreur : mieux vaut refuser que soumettre vers un chemin invente.
    """
    forcee = os.environ.get("ROMEO_SCRATCH", "").strip()
    foyer = os.environ.get("ROMEO_HOME", "").strip()
    if forcee:
        return foyer or posixpath.dirname(forcee) or "/home", forcee, [], ""
    try:
        return session_obj.home, session_obj.scratch, session_obj.path_aliases, ""
    except (SSHError, SSHTimeout):
        if confirm:
            raise
        return "/home/$USER", "/scratch_p/$USER", [], (
            "hors ligne : le scratch n'a pas pu etre interroge, les chemins du "
            "script sont donc illustratifs. Definis ROMEO_SCRATCH pour les "
            "figer, ou reconnecte-toi avant de soumettre."
        )

def _error(message: str, **extra) -> dict:
    """Erreur normalisee : le modele doit pouvoir corriger sans deviner."""
    payload = {"ok": False, "error": message}
    payload.update(extra)
    return payload

def _duree_job(minutes: int, time_limit: str | None, plafond_minutes: int) -> str:
    """Concilie les deux facons d'exprimer la duree d'un job.

    Le serveur exprimait la duree tantot par `time_limit` (une chaine riche :
    « 2h », « 1-00:00:00 »), tantot par `minutes` (un entier). Pour un modele,
    c'etait deux conventions a retenir selon l'outil.

    La regle est desormais : `minutes` ne subsiste que la ou il borne une
    ATTENTE du serveur ; partout ou il s'agit d'une duree de job SLURM,
    `time_limit` fait foi et `minutes` reste accepte comme repli.
    """
    if time_limit:
        demandees = parse_duration(time_limit) // 60
    else:
        demandees = int(minutes)
    return "{}m".format(max(5, min(int(demandees), plafond_minutes)))

def _job_id_depuis_sbatch(sortie_sbatch: str) -> str:
    """Extrait l'identifiant rendu par `sbatch --parsable`, ou une chaine vide.

    `--parsable` rend `<jobid>` ou `<jobid>;<cluster>`. Comme stdout et stderr
    sont fusionnes par le transport, une ligne parasite peut precéder : on ne
    lit que la derniere, et on exige qu'elle soit numerique. Un identifiant
    invente polluerait le registre, pointerait des journaux inexistants et,
    dans une chaine de segments, produirait une dependance impossible a
    satisfaire.
    """
    lignes = [l for l in (sortie_sbatch or "").strip().splitlines() if l.strip()]
    if not lignes:
        return ""
    candidat = lignes[-1].split(";")[0].strip()
    return candidat if candidat.isdigit() else ""

def _soumettre_sbatch(
    s, plan, nom: str, *, note: str = "", options: tuple = (), ecrire: bool = True
) -> dict:
    """Depose le script, le soumet, valide l'identifiant et l'enregistre.

    Cette sequence etait recopiee a l'identique dans sept outils, avec des
    validations inegales : un seul verifiait que l'identifiant etait numerique,
    et aucun ne se premunissait d'une sortie vide : l'acces `[-1]` levait alors
    une IndexError *apres* une soumission reussie, laissant un job sur le
    cluster sans que l'appelant en connaisse le numero.

    Rend soit ``{"ok": True, "job_id", "script_path", "stdout", "stderr"}``,
    soit une erreur structuree.
    """
    chemin_script = posixpath.join(plan.workdir, "{}.sbatch".format(nom))
    try:
        if ecrire:
            s.write_file(chemin_script, plan.script, mode="700")
        from .reproducibility import submission_provenance
        provenance = submission_provenance(s, plan)
        commande = ["sbatch", "--parsable", *options, shlex.quote(chemin_script)]
        resultat = _sh(s, " ".join(commande), timeout=60, cwd=plan.workdir)
    except (SSHError, SSHTimeout) as exc:
        return _error(str(exc), script_path=chemin_script)

    if not resultat.ok:
        # Le script est joint : c'est ce qui permet de comprendre un refus de
        # sbatch sans aller le relire sur le cluster.
        return _error(
            "sbatch a refuse le job : {}".format(resultat.stdout.strip()),
            script_path=chemin_script,
            script=plan.script,
        )

    job_id = _job_id_depuis_sbatch(resultat.stdout)
    if not job_id:
        return _error(
            "reponse inattendue de sbatch : {!r}. Le job a peut-etre ete "
            "soumis : verifie avec list_jobs avant de recommencer.".format(
                resultat.stdout.strip()[:200]
            ),
            script_path=chemin_script,
        )

    sortie_glob = "{}/{}-{}*.out".format(plan.workdir, nom, job_id)
    erreur_glob = "{}/{}-{}*.err".format(plan.workdir, nom, job_id)
    registry().record(
        job_id=job_id, name=nom, partition=plan.partition, arch=plan.arch,
        workdir=plan.workdir, stdout_glob=sortie_glob, stderr_glob=erreur_glob,
        script=plan.script, note=note, provenance=provenance,
    )
    return {
        "ok": True, "job_id": job_id, "script_path": chemin_script,
        "stdout": sortie_glob, "stderr": erreur_glob,
    }

# =============================================================================
# Services interactifs et noeuds de mise au point
# =============================================================================
def _attendre_noeud(s, job_id: str, budget: int = 180) -> str | None:
    """Attend l'affectation d'un noeud et rend son nom, ou None.

    Cette attente survient APRES la soumission. Une erreur de transport ne doit
    donc jamais remonter : elle ferait perdre a l'appelant l'identifiant d'un
    job deja lance, qui continuerait de tourner sans que personne puisse
    l'annuler. L'absence de noeud est un cas nominal, deja traite par les
    appelants.
    """
    limite = time.monotonic() + budget
    while time.monotonic() < limite:
        try:
            resultat = _sh(
                s, "squeue -h -j {} -o '%T|%N'".format(shlex.quote(job_id)),
                timeout=30,
            )
        except (SSHError, SSHTimeout):
            return None
        morceaux = resultat.stdout.strip().split("|")
        if len(morceaux) == 2 and morceaux[0].strip() == "RUNNING" and morceaux[1].strip():
            return morceaux[1].strip()
        time.sleep(5)
    return None

# =============================================================================
# Telemetrie en direct
# =============================================================================
def _srun_overlap(s, job_id: str, commande: str, timeout: int = 120):
    """Execute une sonde dans l'allocation d'un job deja en cours.

    `--overlap` autorise une etape supplementaire a partager les ressources
    deja reservees : la mesure ne consomme donc pas d'allocation propre et
    n'attend pas en file.
    """
    return _sh(
        s,
        "srun --jobid={} --overlap --nodes=1 --ntasks=1 {}".format(
            shlex.quote(job_id), commande
        ),
        timeout=timeout,
        max_chars=12_000,
    )

def _entier(valeur: str):
    try:
        return int(float(valeur))
    except (TypeError, ValueError):
        return None

def _flottant(valeur: str):
    try:
        return round(float(valeur), 1)
    except (TypeError, ValueError):
        return None

def indices_pile(texte: str) -> list[str]:
    """Traduit une trace de pile en hypotheses de blocage."""
    indices = []
    if re.search(r"MPI_|PMPI_|opal_progress|ucp_worker_progress", texte):
        indices.append(
            "Pile arretee dans MPI : interblocage probable, souvent une "
            "collective ou un echange non apparie entre rangs."
        )
    # `cu[A-Z]` vise les appels camelCase du pilote (cuLaunchKernel,
    # cuMemAlloc) et reste donc sensible a la casse. En ignorant la casse, ce
    # motif capturerait n'importe quel mot contenant « cu », par exemple
    # `execute_command_internal`, qui n'a rien a voir avec CUDA.
    if re.search(r"cuda|nccl", texte, re.IGNORECASE) or re.search(
        r"\bcu[A-Z]\w+", texte
    ):
        indices.append(
            "Pile dans CUDA ou NCCL : synchronisation de peripherique ou "
            "collective bloquee. Relance avec nccl_debug=true pour situer."
        )
    if re.search(r"futex|pthread_cond_wait|sem_wait", texte):
        indices.append(
            "Attente sur verrou ou condition : contention entre fils, ou "
            "processus de chargement de donnees a l'arret."
        )
    if re.search(r"\bread\b|\bpread64\b|io_schedule", texte):
        indices.append(
            "Pile en attente d'entree-sortie : le calcul lit le disque. "
            "Confirme avec job_live_metrics, et envisage la mise en cache en "
            "memoire vive."
        )
    return indices

# =============================================================================
# Cache de roues aarch64
# =============================================================================
def _wheelhouse(s, arch: str) -> str:
    return posixpath.join(s.scratch, ".wheels", ARCHS[arch]["uname"])

_LIGNE_STATS = re.compile(
    r"^\s*(\d+[.,]\d+)\s+([\d,]+)\s+([\d,]+)\s+.*?\s{2,}(\S.*?)\s*$"
)


def _resumer_tableau(lignes: list[str], maximum: int = 5) -> list[dict]:
    """Extrait les lignes exploitables d'un tableau `nsys stats`."""
    entrees = []
    for ligne in lignes:
        correspondance = _LIGNE_STATS.match(ligne)
        if not correspondance:
            continue
        pourcentage, total, instances, nom = correspondance.groups()
        entrees.append(
            {
                "part_pct": float(pourcentage.replace(",", ".")),
                "temps_total_ns": int(total.replace(",", "")),
                "appels": int(instances.replace(",", "")),
                "nom": nom.strip()[:90],
            }
        )
        if len(entrees) >= maximum:
            break
    return entrees

def _docs_dir() -> Path:
    """Corpus livre avec le paquet ; surcharge explicite, jamais liee au cwd."""
    override = os.environ.get("ROMEO_DOCS_DIR", "").strip()
    if not override:
        return Path(__file__).resolve().with_name("documentation")
    path = Path(override).expanduser()
    return path if path.is_absolute() else Path(__file__).resolve().parents[1] / path

def _resolve_doc(page: str) -> Path | str:
    """Resout une page de doc en chemin sur, ou rend un message d'erreur."""
    from .docsearch import resolve_page
    try:
        return resolve_page(_docs_dir(), page)
    except ValueError as exc:
        return str(exc)
