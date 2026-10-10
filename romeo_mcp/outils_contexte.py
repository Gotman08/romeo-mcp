"""Ce que le modele lit pour se situer avant d'agir.

Etat du cluster, catalogue logiciel, quotas, verification du modele encode,
ressources MCP et prompts. Aucun de ces outils ne modifie quoi que ce soit.
"""

from __future__ import annotations

import shlex
import time
import threading
from .observability import ReadCache
from .parallel_runtime import parse_spack_catalog
from typing import Any
from .cluster import (
    ARCHS,
    DEFAULT_ACCOUNT,
    MISSING_TOOLS,
    PARTITIONS,
    TOOLS_VIA_SPACK,
    cheatsheet,
    format_slurm_time,
)
from .verification import SONDE as SONDE_VERIFICATION, analyser_releve
from . import docsearch
from .ssh import SSHError, SSHTimeout, session
from .noyau import (
    MAX_WAIT_SECONDS,
    READ_ONLY,
    _docs_dir,
    _error,
    _resolve_doc,
    _sh,
    outil,
    server,
)


# =============================================================================
# Contexte cluster
# =============================================================================
@outil(
    annotations=READ_ONLY,
    description=(
        "Etat de ROMEO en un appel : partitions, noeuds libres par architecture, "
        "tes jobs en cours et ta part d'ordonnancement. A appeler avant de "
        "dimensionner un job."
    ),
)
def romeo_status(include_queue: bool = True, max_age_seconds: int = 0) -> dict[str, Any]:
    """Situation complete du cluster en une seule aller-retour SSH."""
    s = session()
    if not 0 <= max_age_seconds <= 60:
        return _error("max_age_seconds doit etre compris entre 0 et 60 ; 0 force une lecture actuelle.")
    cache_key = (s.host, s.user, DEFAULT_ACCOUNT, include_queue)
    cached = _STATUS_CACHE.get(cache_key, max_age_seconds)
    if cached is not None:
        value, age = cached
        value["observation"].update(cached=True, age_seconds=age, current_state_observed=False)
        return value
    # `sinfo -N` liste un noeud par partition d'appartenance : le dedoublonnage
    # se fait plus bas, par nom. S'appuyer sur une partition supposee couvrir
    # tout le parc etait fragile : la creation d'une partition, ou le retrait
    # d'un noeud de `instant`, l'aurait rendu faux en silence.
    command = (
        "echo '###NODES'; sinfo -h -N -o '%n|%T|%f' || exit $?; "
        "echo '###PART'; sinfo -h -o '%P|%a|%l' || exit $?; "
        "echo '###SHARE'; sshare -U -n -P -o Account,EffectvUsage,FairShare || exit $?"
    )
    if include_queue:
        command += "; echo '###QUEUE'; squeue -h -u $USER -o '%i|%j|%P|%T|%M|%L|%R' || exit $?"

    try:
        result = _sh(s, command, timeout=45, max_chars=60_000, read_only=True)
    except (SSHError, SSHTimeout) as exc:
        return _error(str(exc))

    if not result.ok or result.truncated:
        return _error("Etat du cluster incomplet ; aucune absence de ressources n'est deduite.", truncated=result.truncated)

    sections: dict[str, list[str]] = {}
    current = None
    for line in result.stdout.splitlines():
        if line.startswith("###"):
            current = line[3:].strip()
            sections[current] = []
        elif current:
            sections[current].append(line)

    # -- inventaire des noeuds, dedoublonne --------------------------------
    inventory: dict[str, dict] = {
        key: {"total": 0, "idle": 0, "mixed": 0, "allocated": 0, "unavailable": 0}
        for key in ARCHS
    }
    seen: set[str] = set()
    for line in sections.get("NODES", []):
        parts = line.split("|")
        if len(parts) < 3:
            continue
        node, state, feature = parts[0].strip(), parts[1].strip().lower(), parts[2].strip()
        if node in seen or feature not in inventory:
            continue
        seen.add(node)
        bucket = inventory[feature]
        bucket["total"] += 1
        if state.startswith("idle"):
            bucket["idle"] += 1
        elif state.startswith("mix"):
            bucket["mixed"] += 1
        elif state.startswith("alloc"):
            bucket["allocated"] += 1
        else:  # drained, down, planned, reserved...
            bucket["unavailable"] += 1

    for key, bucket in inventory.items():
        bucket["gpus_idle"] = bucket["idle"] * ARCHS[key]["gpus_per_node"]
        bucket["cpus_idle"] = bucket["idle"] * ARCHS[key]["cpus_per_node"]

    # -- partitions ---------------------------------------------------------
    partitions = []
    for line in sections.get("PART", []):
        parts = line.split("|")
        if len(parts) >= 3:
            partitions.append(
                {
                    "name": parts[0].strip().rstrip("*"),
                    "available": parts[1].strip(),
                    "time_limit": parts[2].strip(),
                }
            )

    # -- part d'ordonnancement ---------------------------------------------
    fairshare = []
    for line in sections.get("SHARE", []):
        parts = line.split("|")
        if len(parts) >= 3 and parts[0].strip():
            fairshare.append(
                {
                    "account": parts[0].strip(),
                    "usage": parts[1].strip(),
                    "fairshare": parts[2].strip(),
                }
            )

    # -- file personnelle ---------------------------------------------------
    queue = []
    for line in sections.get("QUEUE", []):
        parts = line.split("|")
        if len(parts) >= 7:
            queue.append(
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

    value = {
        "ok": True,
        "host": s.host,
        "user": s.user,
        "account": DEFAULT_ACCOUNT,
        "nodes": inventory,
        "partitions": partitions,
        "fairshare": fairshare,
        "my_jobs": queue if include_queue else None,
        "observation": {"observed_at": time.time(), "age_seconds": 0, "cached": False, "current_state_observed": True},
        "note": (
            "gpus_idle et cpus_idle ne comptent que les noeuds entierement "
            "libres ; les noeuds en etat `mixed` offrent encore des ressources."
        ),
    }
    _STATUS_CACHE.put(cache_key, value)
    return value

@outil(
    annotations=READ_ONLY,
    description=(
        "Liste les modules Environment Modules, herites de l'ancien "
        "calculateur. Sur ROMEO 2025 la voie officielle est Spack : utilise "
        "`romeo_software` en premier lieu, et ne recours aux modules que si un "
        "logiciel n'existe pas dans le catalogue Spack."
    ),
)
def romeo_modules(search: str = "") -> dict[str, Any]:
    """Recherche dans `module avail`."""
    s = session()
    try:
        result = _sh(s, "module -t avail 2>&1", timeout=40, max_chars=40_000)
    except (SSHError, SSHTimeout) as exc:
        return _error(str(exc))

    names = [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip() and not line.strip().endswith(":") and "/" not in line[:1]
    ]
    names = [n for n in names if not n.startswith("-")]
    if search:
        needle = search.lower()
        names = [n for n in names if needle in n.lower()]

    return {"ok": True, "count": len(names), "modules": sorted(set(names))}

#: Catalogue Spack borne, avec duree de vie explicite et isolation par cible.
_SPACK_CACHE = ReadCache(capacity=8)
_STATUS_CACHE = ReadCache(capacity=8)
_SPACK_LOCK = threading.RLock()
# Les catalogues --deps reels depassent 1,8 Mo. Garder une borne explicite
# avec de la marge ; une observation tronquee n'est jamais mise en cache.
_SPACK_MAX_CHARS = 8 * 1024 * 1024

@outil(
    annotations=READ_ONLY,
    description=(
        "Cherche un logiciel dans le catalogue Spack de ROMEO, plusieurs centaines "
        "de paquets qui constituent la voie officielle de chargement des "
        "logiciels. ATTENTION : le catalogue differe selon l'architecture. Des "
        "outils absents du PATH du noeud de login (conda via `anaconda3`, "
        "`apptainer`, plusieurs versions de `cuda`) s'y trouvent. Les paquets "
        "trouves se passent ensuite a job_prepare ou compute_command_prepare via "
        "`spack_packages`."
    ),
)
def romeo_software(search: str = "", arch: str = "armgpu", limit: int = 40,
                   max_age_seconds: int = 300, refresh: bool = False) -> dict[str, Any]:
    """Interroge le catalogue Spack de l'architecture demandee."""
    s = session()
    key = str(arch).strip().lower()
    if key not in ARCHS:
        return _error(
            "architecture inconnue : {!r}. Valeurs : x64cpu, armgpu.".format(arch)
        )
    node = ARCHS[key]
    if not 0 <= max_age_seconds <= 3600:
        return _error("max_age_seconds doit etre compris entre 0 et 3600.")
    cache_key = (s.host, s.user, key)
    with _SPACK_LOCK:
        return _software_catalog(s, key, node, cache_key, search, limit, max_age_seconds, refresh)


def _software_catalog(s, key, node, cache_key, search, limit, max_age_seconds, refresh):
    cached = _SPACK_CACHE.get(cache_key, 0 if refresh else max_age_seconds)

    if cached is None:
        try:
            # Le `2>/dev/null` d'origine masquait l'echec du chargement
            # d'environnement : `spack` restait absent du PATH, la sortie etait
            # vide, et un catalogue vide se figeait dans le cache pour toute la
            # vie du processus. L'outil affirmait alors qu'aucun logiciel
            # n'existe, exactement l'erreur qu'il devait empecher. stderr est
            # deja fusionne par le transport. Le parseur conserve les details
            # JSON (empreintes, variantes et dependances).
            result = _sh(
                s,
                "{} >/dev/null || exit $?; spack find --json --deps".format(node["env_loader"]),
                timeout=180,
                max_chars=_SPACK_MAX_CHARS,
                read_only=True,
            )
        except (SSHError, SSHTimeout) as exc:
            return _error(str(exc))

        if not result.ok or result.truncated:
            return _error(
                "`spack find` a echoue sur {} (code {}). Le catalogue n'est pas "
                "mis en cache : corrige la cause puis relance.".format(
                    key, result.rc
                ),
                detail=result.stdout.strip()[:300],
            )
        try:
            specifications = parse_spack_catalog(result.stdout)
        except ValueError as exc:
            return _error(str(exc))
        catalogue = [item["package"] for item in specifications]
        if not catalogue:
            return _error(
                "`spack find` n'a rien renvoye d'exploitable pour {} : ne "
                "conclus pas que les logiciels sont absents.".format(key),
                detail=result.stdout.strip()[:300],
            )
        # On ne memorise qu'un catalogue reellement obtenu.
        observation = {"packages": catalogue, "specifications": specifications, "observed_at": time.time()}
        _SPACK_CACHE.put(cache_key, observation)
        age = 0
    else:
        observation, age = cached

    specifications = observation["specifications"]
    needle = (search or "").strip().lower()
    if needle:
        specifications = [p for p in specifications if needle in str(p).lower()]
    packages = [p["package"] for p in specifications]

    limit = max(1, min(int(limit), 200))
    shown = packages[:limit]
    return {
        "ok": True,
        "arch": key,
        "env_loader": node["env_loader"],
        "search": search,
        "total_in_catalog": len(observation["packages"]),
        "observation": {"observed_at": observation["observed_at"], "age_seconds": age, "cached": cached is not None},
        "count": len(packages),
        "truncated": len(packages) > limit,
        "packages": shown,
        "specifications": specifications[:limit],
        "details_available": all(p["details_available"] for p in specifications[:limit]),
        "dependency_records_included": True,
        "mpi_guidance": "OpenMPI sur x64cpu ; NVHPC/HPC-X sur armgpu. Charger une empreinte /hash pour fixer l'installation.",
        "usage": (
            "Passe ces noms a job_prepare(spack_packages=[...]) ou "
            "compute_command_prepare(spack_packages=[...]) : le script generera "
            "`{}` puis `spack load`.".format(node["env_loader"])
        ),
    }

@outil(
    annotations=READ_ONLY,
    description=(
        "Quotas de stockage reels, par espace (home, scratch, projet), lus avec "
        "`mmlsquota`. Signale les depassements de quota souple et l'expiration "
        "du delai de grace, qui bloque l'ecriture. A consulter avant de produire "
        "des sorties volumineuses."
    ),
)
def romeo_quota(project: str = "") -> dict[str, Any]:
    """Etat des quotas GPFS.

    `df` serait trompeur ici : il rapporte les 2,8 Po du systeme de fichiers
    partage, pas la part de l'utilisateur. Seul `mmlsquota` donne les plafonds
    reels et l'etat du delai de grace.
    """
    s = session()
    command = "mmlsquota --block-size auto gpfs 2>&1"
    if project.strip():
        command += "; echo '###PROJECT'; mmlsquota --block-size auto -g {} gpfs 2>&1".format(
            shlex.quote(project.strip())
        )

    try:
        result = _sh(s, command, timeout=90, max_chars=12_000)
    except (SSHError, SSHTimeout) as exc:
        return _error(str(exc))
    if not result.ok:
        return _error(
            "mmlsquota indisponible : {}".format(result.stdout.strip()[:300])
        )

    filesets = []
    alerts = []
    for line in result.stdout.splitlines():
        parts = line.split()
        # Format : Filesystem Fileset type blocks quota limit in_doubt grace ...
        if len(parts) < 8 or parts[0] != "gpfs":
            continue
        fileset, kind = parts[1], parts[2]
        blocks, soft, hard, in_doubt, grace = parts[3:8]
        entry = {
            "espace": fileset,
            "type": kind,
            "utilise": blocks,
            "quota_souple": soft,
            "quota_strict": hard,
            "en_attente": in_doubt,
            "delai_de_grace": grace,
        }
        filesets.append(entry)

        if grace.lower() == "expired":
            alerts.append(
                "`{}` : quota souple ({}) depasse, utilise {}, et le delai de "
                "grace est EXPIRE. L'ecriture peut etre refusee meme sous le "
                "quota strict ({}). Fais du menage ou demande un relevement par "
                "ticket.".format(fileset, soft, blocks, hard)
            )
        elif grace.lower() not in ("none", "-", ""):
            alerts.append(
                "`{}` : quota souple depasse, delai de grace en cours ({}). "
                "Reviens sous {} avant expiration.".format(fileset, grace, soft)
            )

    return {
        "ok": True,
        "user": s.user,
        "filesets": filesets,
        "alerts": alerts,
        "paths": {
            "home": s.home,
            "scratch": s.scratch,
            "project": "/project/<code_projet>",
        },
        "advice": (
            "Les quotas peuvent differer entre home, scratch et projet : utilise "
            "les valeurs relevees ci-dessus. /scratch_p/$USER est l'espace des "
            "calculs en cours ; /project contient les donnees partagees, "
            "comptabilisees au groupe du projet."
        ),
    }

# =============================================================================
# Ressources
# =============================================================================
@server.resource(
    "romeo://cheatsheet",
    name="Aide-memoire ROMEO",
    description=(
        "Partitions, architectures, comptes, stockage et pieges du cluster. "
        "A lire avant de dimensionner un job."
    ),
    mime_type="text/markdown",
)
def cheatsheet_resource() -> str:
    return cheatsheet()

@server.resource(
    "romeo://docs",
    name="Documentation officielle ROMEO",
    description=(
        "Index de la documentation officielle scrapee localement, si elle est "
        "presente sur la machine."
    ),
    mime_type="text/markdown",
)
def docs_index() -> str:
    directory = _docs_dir()
    if not directory.is_dir():
        return (
            "# Documentation ROMEO absente\n\n"
            "Aucun dossier trouve en `{}`.\n\n"
            "Reinstalle le paquet avec son dossier `documentation`, ou verifie "
            "la variable d'environnement `ROMEO_DOCS_DIR`. La collecte se fait "
            "avec `tools/romeo_doc_scraper.py`.\n\n"
            "En attendant, la ressource `romeo://cheatsheet` couvre "
            "l'essentiel du cluster.".format(directory)
        )

    # Le sommaire reconstruit par le scraper reproduit l'arborescence officielle
    # du site : il informe bien mieux qu'une liste de fichiers a plat.
    sommaire = directory / "SOMMAIRE.md"
    if sommaire.is_file():
        return sommaire.read_text(encoding="utf-8")

    pages = sorted(p.relative_to(directory).as_posix() for p in directory.rglob("*.md"))
    if not pages:
        return "# Documentation ROMEO\n\nDossier `{}` present mais vide.".format(directory)
    lines = ["# Documentation ROMEO", "", "Pages disponibles :", ""]
    lines += ["- `romeo://docs/{}`".format(page) for page in pages[:200]]
    if len(pages) > 200:
        lines.append("- ... et {} autres".format(len(pages) - 200))
    return "\n".join(lines)

# `{+page}` et non `{page}` : l'expansion reservee de la RFC 6570 traverse les
# barres obliques, sans quoi les pages imbriquees comme
# `ressources/romeo_2025/lancer_un_calcul.md` seraient inaccessibles.
@server.resource(
    "romeo://docs/{+page}",
    name="Page de documentation ROMEO",
    description="Contenu d'une page de la documentation officielle scrapee.",
    mime_type="text/markdown",
)
def docs_page(page: str) -> str:
    resolved = _resolve_doc(page)
    if isinstance(resolved, str):
        return resolved
    return resolved.read_text(encoding="utf-8")

@outil(
    annotations=READ_ONLY,
    description=(
        "Recherche locale classee par pertinence dans la documentation ROMEO "
        "livree avec le MCP. Accepte mots-cles ou questions, sans distinction "
        "d'accents/casse. mode='phrase' cherche un motif exact. page_prefix "
        "restreint une branche (ex. ressources/romeo_2025/). max_chars borne "
        "le total des extraits. Chaque resultat donne source, titres, lignes "
        "et read_args pour lire la section complete. Suivre next_call pour "
        "parcourir les autres resultats sans perte par troncature."
    ),
)
def search_docs(query: str, max_results: int = 20, context_lines: int = 2,
                max_chars: int = 18000, page_prefix: str = "", mode: str = "terms",
                offset: int = 0, expected_revision: str = "") -> dict[str, Any]:
    """Recherche lexicale par sections ; aucune dependance reseau ni SSH."""
    try:
        return docsearch.search(_docs_dir(), query, max_results, context_lines,
                                max_chars, page_prefix, mode, offset, expected_revision)
    except (ValueError, OSError, UnicodeError) as exc:
        return _error(str(exc))

@outil(
    annotations=READ_ONLY,
    description=(
        "Lit le texte original d'une page locale ROMEO. Utiliser les read_args "
        "de search_docs ou choisir start_line/end_line (inclusives, base 1). "
        "max_chars borne la reponse. Si truncated=true, rappeler avec next_call "
        "pour recuperer la suite exacte ; offset est relatif a la plage choisie. "
        "expected_sha256 detecte un changement de page entre deux lectures."
    ),
)
def read_doc(page: str, max_chars: int = 12000, start_line: int = 1,
             end_line: int | None = None, offset: int = 0,
             expected_sha256: str = "") -> dict[str, Any]:
    """Lecture bornee, sans texte perdu entre les pages de resultat."""
    try:
        return docsearch.read_page(_docs_dir(), page, max_chars, start_line,
                                   end_line, offset, expected_sha256)
    except (ValueError, OSError, UnicodeError) as exc:
        return _error(str(exc))

@server.resource(
    "romeo://limits",
    name="Limites et outils manquants",
    description="Ce que ROMEO ne propose pas, et par quoi le remplacer.",
    mime_type="text/markdown",
)
def limits_resource() -> str:
    return "\n".join(
        [
            "# Limites connues de ROMEO",
            "",
            "## Outils reellement absents",
            "",
            *("- `{}`".format(tool) for tool in MISSING_TOOLS),
            "",
            "- Pas de `seff` : utilise l'outil `job_efficiency`, qui recalcule "
            "les memes metriques depuis `sacct`.",
            "",
            "## Faussement absents : disponibles via Spack",
            "",
            "Un `command -v` sur le noeud de login ne les voit pas, mais ils "
            "existent dans le catalogue Spack de chaque architecture :",
            "",
            *(
                "- `{}` -> paquet `{}`".format(name, package)
                for name, package in TOOLS_VIA_SPACK.items()
            ),
            "",
            "Cherche-les avec `romeo_software`, puis passe-les en "
            "`spack_packages` a `job_prepare` ou `compute_command_prepare`.",
            "",
            "## Limites de temps",
            "",
            *(
                "- `{}` : {}".format(name, format_slurm_time(p["max_seconds"]))
                for name, p in PARTITIONS.items()
            ),
            "",
            "## Plafonds imposes par ce serveur MCP",
            "",
            "- Commande sur le noeud de login : 20 s maximum, calculs refuses.",
            "- `wait_for_job` : {} s maximum.".format(MAX_WAIT_SECONDS),
            "- `compute_command_run` : soumission asynchrone ; la duree vient du plan.",
        ]
    )

@server.resource(
    "romeo://jobs/running",
    name="Jobs en cours",
    description="Etat instantane de tes jobs dans la file SLURM.",
    mime_type="text/markdown",
)
def jobs_running() -> str:
    """Vue courante de la file personnelle, relue a chaque lecture."""
    try:
        s = session()
        resultat = _sh(
            s,
            "squeue -h -u $USER -o '%i|%j|%P|%T|%M|%L|%D|%R'",
            timeout=35,
            max_chars=20_000,
        )
    except (SSHError, SSHTimeout) as exc:
        return "# Jobs en cours\n\nLecture impossible : {}".format(exc)

    lignes = [l for l in resultat.stdout.splitlines() if l.strip()]
    if not lignes:
        return "# Jobs en cours\n\nAucun job dans la file."

    sortie = [
        "# Jobs en cours",
        "",
        "| Job | Nom | Partition | Etat | Ecoule | Restant | Noeuds | Motif |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for ligne in lignes:
        champs = [c.strip() for c in ligne.split("|")]
        if len(champs) >= 8:
            sortie.append("| " + " | ".join(champs[:8]) + " |")
    return "\n".join(sortie)

@server.resource(
    "romeo://cluster/load",
    name="Charge du cluster",
    description="Occupation instantanee des noeuds et des GPU, par architecture.",
    mime_type="text/markdown",
)
def cluster_load() -> str:
    """Occupation du parc, utile pour choisir entre attendre et redimensionner."""
    etat = romeo_status(include_queue=False)
    if not etat.get("ok"):
        return "# Charge du cluster\n\nLecture impossible : {}".format(
            etat.get("error")
        )

    lignes = [
        "# Charge du cluster",
        "",
        "| Architecture | Libres | Partiels | Occupes | Indisponibles | GPU libres |",
        "|---|---|---|---|---|---|",
    ]
    for cle, seau in (etat.get("nodes") or {}).items():
        lignes.append(
            "| `{}` | {} | {} | {} | {} | {} |".format(
                cle,
                seau.get("idle", 0),
                seau.get("mixed", 0),
                seau.get("allocated", 0),
                seau.get("unavailable", 0),
                seau.get("gpus_idle", 0),
            )
        )
    lignes += [
        "",
        "Les noeuds `partiels` offrent encore des ressources : un job modeste "
        "peut y demarrer immediatement.",
    ]
    return "\n".join(lignes)

# =============================================================================
# Verification du modele encode
# =============================================================================
@outil(
    annotations=READ_ONLY,
    description=(
        "Confronte le modele de cluster encode dans ce serveur a la realite de "
        "SLURM : partitions et limites de temps, comptes de noeuds par "
        "architecture, capacites d'un noeud, plafonds du compte, outils "
        "declares absents. Rend les ecarts, sans rien corriger. A lancer quand "
        "un refus de dimensionnement parait injustifie, ou apres une "
        "maintenance du cluster."
    ),
)
def romeo_selfcheck() -> dict[str, Any]:
    """Ecarts entre le modele encode et le cluster observe."""
    s = session()
    releve = _sh(s, SONDE_VERIFICATION, timeout=60, max_chars=40_000)
    if not releve.ok:
        return _error(
            "releve impossible : {}".format(releve.stdout.strip()[:200] or "aucune sortie")
        )
    racines = {
        "home": [s.home, *s.home_aliases],
        "scratch": [s.scratch, *s.scratch_aliases],
    }
    return analyser_releve(releve.stdout, racines)

# =============================================================================
# Prompts
# =============================================================================
@server.prompt(
    name="optimize_for_gh200",
    title="Optimiser un script pour les GH200",
    description="Adapte un script Python aux noeuds Grace Hopper aarch64 de ROMEO.",
)
def prompt_optimize_gh200(script_path: str = "") -> str:
    cible = script_path or "le script indique par l'utilisateur"
    return (
        "Analyse {} et propose les modifications permettant de tirer parti des "
        "noeuds Grace Hopper de ROMEO.\n\n"
        "Contraintes de la machine, a verifier une par une :\n"
        "- Architecture **aarch64** : toute roue Python ou bibliotheque native "
        "doit exister pour arm64. Verifie les dependances qui n'ont que des "
        "roues x86_64 et propose une alternative.\n"
        "- GPU **GH200**, capacite de calcul **sm_90**, environ 96 Gio de VRAM "
        "par carte, 4 cartes par noeud.\n"
        "- Processeur **Grace** : 288 coeurs par noeud, donc un chargement de "
        "donnees genereux est possible ; regle le nombre de processus de "
        "chargement en consequence plutot que de le laisser a 0.\n"
        "- La memoire est unifiee entre Grace et Hopper : les transferts "
        "hote-peripherique coutent moins cher qu'usuellement, ce qui change "
        "l'arbitrage sur le pre-chargement.\n\n"
        "Points a examiner : precision mixte bf16, `torch.compile`, taille de "
        "lot au regard des 96 Gio, `gradient checkpointing`, format des donnees "
        "en entree, et fixation de `TORCH_CUDA_ARCH_LIST=9.0` a la compilation.\n\n"
        "Verifie les faits du cluster avec l'outil `romeo_software` avant de "
        "proposer un paquet, et consulte `search_docs` pour la procedure "
        "officielle d'installation de PyTorch sur ARM.".format(cible)
    )

@server.prompt(
    name="debug_slurm_failure",
    title="Diagnostiquer un job SLURM en echec",
    description="Enquete guidee sur un job termine anormalement.",
)
def prompt_debug_slurm(job_id: str = "") -> str:
    reference = job_id or "le job indique par l'utilisateur"
    return (
        "Diagnostique l'echec de {}. Procede dans cet ordre, sans sauter "
        "d'etape :\n\n"
        "1. `diagnose_job` : il combine l'etat SLURM, la fin des journaux et la "
        "reconnaissance des modes d'echec connus. C'est le point de depart, pas "
        "un complement.\n"
        "2. Si une cause est identifiee, applique le remede propose et explique "
        "a l'utilisateur pourquoi cette cause explique ce symptome.\n"
        "3. Si aucune cause n'est reconnue, lis la sortie complete avec "
        "`job_log_tail(stream='both')` puis le script soumis.\n"
        "4. Dans tous les cas, termine par `job_efficiency` : un job peut "
        "avoir echoue pour une raison evidente tout en revelant un "
        "dimensionnement a corriger.\n\n"
        "Rappel du piege le plus frequent sur ROMEO : un binaire ou une roue "
        "Python construits sur le noeud de login (x86_64) et executes sur un "
        "noeud GPU (aarch64) echouent avec une instruction illegale.".format(
            reference
        )
    )

@server.prompt(
    name="scale_to_multi_node",
    title="Passer un script en multi-noeuds",
    description="Adapte un entrainement mono-noeud vers plusieurs noeuds GPU.",
)
def prompt_scale_multi_node(script_path: str = "", nodes: str = "2") -> str:
    cible = script_path or "le script indique par l'utilisateur"
    return (
        "Adapte {} pour un entrainement reparti sur {} noeuds GPU de ROMEO.\n\n"
        "Ce que le serveur prend deja en charge, et que tu n'as donc pas a "
        "ecrire a la main : `job_prepare(distributed=...)` genere `MASTER_ADDR` "
        "depuis le premier noeud alloue, `MASTER_PORT`, `WORLD_SIZE`, et le "
        "lanceur adapte. Choisis la famille :\n"
        "- `ddp` : torchrun deploie un processus par GPU, une tache SLURM par "
        "noeud.\n"
        "- `accelerate` : meme principe avec le lanceur Hugging Face.\n"
        "- `deepspeed` ou `srun` : une tache SLURM par GPU, les rangs venant "
        "de SLURM.\n\n"
        "Ce qui reste a ta charge dans le code : initialisation du groupe de "
        "processus, enveloppe du modele, echantillonneur distribue, reduction "
        "des metriques, et sauvegarde depuis le seul rang 0.\n\n"
        "Verifie enfin la coherence du dimensionnement : {} noeuds a 4 GPU "
        "restent sous le plafond de 60 GPU du compte, mais la partition "
        "choisie doit exposer assez de noeuds : `job_prepare` le controle et "
        "refuse le cas echeant.".format(cible, nodes, nodes)
    )

if __name__ == "__main__":
    main()
