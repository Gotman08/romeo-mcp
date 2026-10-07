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
import re
import shlex
import time
from pathlib import Path
from .profiles import ProfiledServer
# Reexports des appuis historiques ; leur implementation ne depend plus du MCP.
from .execution_backend import (
    _sh, _doublon_recent, _contexte_chemins, _error, _duree_job,
    _job_id_depuis_sbatch, _soumettre_sbatch, _controle_du_script_genere,
)
from mcp.types import ToolAnnotations
from .cluster import ClusterError
from .guard import GuardError
from .registry import registry
from .ssh import SSHError, SSHTimeout, session
from . import __version__
from .observability import TIMINGS


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
  au catalogue, appelle `tool_profile_set` avec profile="full", puis relis tools/list.
- Le noeud de login est en x86_64, les noeuds GPU sont en aarch64. Ne compile
  et n'installe jamais depuis le login : prepare un environnement, des paquets ou des roues avec les outils `python_*`.
  Les commandes arbitraires utilisent `compute_command_prepare` puis `compute_command_run` dans le profil expert.
- Les logiciels se chargent via Spack, propre a chaque architecture. Cherche-les
  avec `romeo_software`, puis passe-les en `spack_packages`. Ne conclus jamais
  qu'un outil est absent parce que `command -v` ne le trouve pas sur le login.
- Aucun calcul sur le noeud de login. Tout passe par `job_prepare`.
- ROMEO est un calculateur generaliste : chimie, mecanique des fluides,
  bio-informatique, statistique, apprentissage automatique. Le parallelisme
  courant est MPI (`distributed='mpi'`, simple prefixe srun). Les options
  propres a PyTorch, aux conteneurs ou aux caches Python sont facultatives et
  desactivees par defaut : ne les active que si la charge de travail les
  concerne reellement.
- `job_prepare` conserve le script exact et rend un plan_id. Relis ce plan,
  puis utilise `job_submit(plan_id=..., confirm=true)` pour le soumettre.
  Meme parcours pour job_array_prepare/job_array_submit et job_pipeline_prepare/job_pipeline_submit.
  La preparation ecrit seulement un plan local ; la soumission modifie ROMEO.
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
DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True)

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
            started = time.monotonic()
            failed = True
            try:
                result = fonction(*args, **kwargs)
                failed = result.get("ok", True) is False
                return result
            except (SSHError, SSHTimeout, ClusterError, GuardError, ValueError) as exc:
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
            finally:
                TIMINGS.record(fonction.__name__, time.monotonic() - started, failed)
        if inspect.iscoroutinefunction(fonction):
            @functools.wraps(fonction)
            async def enveloppe(*args, **kwargs):
                started = time.monotonic()
                failed = True
                try:
                    result = await fonction(*args, **kwargs)
                    failed = result.get("ok", True) is False
                    return result
                except (SSHError, SSHTimeout, ClusterError, GuardError, ValueError) as exc:
                    return _error(str(exc))
                except Exception as exc:
                    return _error("erreur inattendue dans {} : {}".format(
                        fonction.__name__, type(exc).__name__), inattendu=True)
                finally:
                    TIMINGS.record(fonction.__name__, time.monotonic() - started, failed)
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

#: Nom d'un enchainement : repertoire et prefixe de ses jobs.
_NOM_ENCHAINEMENT = re.compile(r"^[A-Za-z0-9._-]{1,48}$")

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
# Resume des tableaux de profilage
# =============================================================================

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
