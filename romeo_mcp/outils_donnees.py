"""Fichiers, stockage, secrets, et verification statique des scripts.

Tout ce qui touche au contenu depose sur le cluster plutot qu'aux calculs.
"""

from __future__ import annotations

import posixpath
import re
import shlex
from typing import Any
from pathlib import Path
from . import files
from .cluster import DEFAULT_ACCOUNT, ClusterError
from .guard import GuardError, allowed_roots, check_path
from .slurm import JobSpec, plan_job
from .ssh import SSHError, SSHTimeout, session
from .noyau import (
    MAX_CHEMINS_VERIFIES,
    MAX_VARIABLES_SIGNALEES,
    MUTATING,
    READ_ONLY,
    _duree_job,
    _error,
    _sh,
    _soumettre_sbatch,
    outil,
)


# =============================================================================
# Fichiers
# =============================================================================
@outil(
    annotations=READ_ONLY,
    description="Contenu d'un repertoire distant (taille et date incluses).",
)
def list_dir(path: str = ".", limit: int = 100) -> dict[str, Any]:
    """Liste un repertoire, borne en nombre d'entrees."""
    s = session()
    try:
        target = check_path(path, s.home, s.scratch, s.path_aliases)
    except GuardError as exc:
        return _error(str(exc))

    limit = max(1, min(int(limit), 500))
    try:
        # Le repertoire est teste avant d'etre liste : avec un simple
        # `ls ... | head`, le code de retour lu est celui de `head`, toujours
        # nul. Un chemin inexistant passait donc pour un succes, et le message
        # « ls: cannot access ...: No such file or directory » etait decoupe en
        # huit colonnes puis rendu comme une entree de fichier.
        result = _sh(
            s,
            "test -d {q} || {{ echo INEXISTANT; exit 2; }}; "
            "ls -lAh --time-style=long-iso {q} 2>&1 | head -n {n}".format(
                q=shlex.quote(target), n=limit + 1
            ),
            timeout=40,
            max_chars=20_000,
        )
    except (SSHError, SSHTimeout) as exc:
        return _error(str(exc))
    if not result.ok or result.stdout.strip().startswith("INEXISTANT"):
        return _error(
            "repertoire introuvable ou illisible : {}".format(target),
            path=target,
            detail=result.stdout.strip()[:200],
        )

    entries = []
    for line in result.stdout.splitlines():
        parts = line.split(None, 7)
        if len(parts) < 8 or line.startswith("total"):
            continue
        entries.append(
            {
                "name": parts[7],
                "size": parts[4],
                "modified": "{} {}".format(parts[5], parts[6]),
                "is_dir": line.startswith("d"),
            }
        )
    return {"ok": True, "path": target, "count": len(entries), "entries": entries}

@outil(
    annotations=READ_ONLY,
    description=(
        "Lit une tranche d'un fichier distant. Toujours borne : precise offset "
        "et limit plutot que de rapatrier un fichier entier."
    ),
)
def read_remote_file(
    path: str, offset: int = 1, limit: int = 200, max_chars: int = 8000
) -> dict[str, Any]:
    """Lit `limit` lignes a partir de la ligne `offset` (1-indexee)."""
    s = session()
    try:
        target = check_path(path, s.home, s.scratch, s.path_aliases)
    except GuardError as exc:
        return _error(str(exc))

    offset = max(1, int(offset))
    limit = max(1, min(int(limit), 2000))
    try:
        result = _sh(
            s,
            "sed -n '{start},{end}p' {path}".format(
                start=offset, end=offset + limit - 1, path=shlex.quote(target)
            ),
            timeout=45,
            max_chars=max_chars * 2,
        )
        total = _sh(s, "wc -l < {}".format(shlex.quote(target)), timeout=30)
    except (SSHError, SSHTimeout) as exc:
        return _error(str(exc))
    if not result.ok:
        return _error(result.stdout.strip() or "fichier illisible", path=target)

    content = result.stdout
    truncated = len(content) > max_chars
    if truncated:
        content = content[:max_chars] + "\n[... tronque ...]"

    return {
        "ok": True,
        "path": target,
        "offset": offset,
        "limit": limit,
        "total_lines": total.stdout.strip() if total.ok else None,
        "truncated": truncated,
        "content": content,
    }

@outil(
    annotations=MUTATING,
    description="Ecrit ou remplace un fichier texte distant (script, configuration).",
)
def write_remote_file(path: str, content: str) -> dict[str, Any]:
    """Depose un fichier sur ROMEO."""
    s = session()
    try:
        target = check_path(path, s.home, s.scratch, s.path_aliases)
        s.write_file(target, content)
    except (GuardError, SSHError, SSHTimeout) as exc:
        return _error(str(exc))
    return {"ok": True, "path": target, "bytes": len(content.encode("utf-8"))}

@outil(
    annotations=MUTATING,
    description="Envoie un fichier ou un repertoire local vers ROMEO.",
)
def upload_to_romeo(local_path: str, remote_path: str, verify: bool = True) -> dict[str, Any]:
    """Transfert montant, avec controle d'integrite de bout en bout."""
    s = session()
    try:
        target = check_path(remote_path, s.home, s.scratch, s.path_aliases)
        resultat = files.upload(s.host, local_path, target)
    except (GuardError, SSHError) as exc:
        return _error(str(exc))

    reponse = {"ok": True, **resultat}
    source = Path(local_path).expanduser()
    if not verify or source.is_dir():
        reponse["verifie"] = False
        if source.is_dir():
            reponse["note"] = ("controle d'integrite non applique a un "
                               "repertoire : verifie un fichier precis au besoin.")
        return reponse

    # Un transfert tronque ou corrompu produit un binaire qui echouera plus
    # tard de facon opaque : mieux vaut le savoir maintenant.
    try:
        locale = files.empreinte_locale(source)
        distante = _sh(s, files.commande_empreinte(target), timeout=300)
    except (OSError, SSHError, SSHTimeout) as exc:
        reponse["verifie"] = False
        reponse["avertissement"] = "controle impossible : {}".format(exc)
        return reponse

    distante_hex = files.empreinte_depuis_sortie(distante.stdout) if distante.ok else ""
    reponse["empreinte_locale"] = locale
    reponse["empreinte_distante"] = distante_hex
    # Empreinte illisible et empreintes differentes sont deux diagnostics
    # opposes : le premier n'est pas un probleme de transfert, et relancer ne
    # le resoudra jamais.
    if not distante_hex:
        reponse["verifie"] = False
        reponse["avertissement"] = (
            "impossible de lire l'empreinte distante : {}".format(
                distante.stdout.strip()[:200] or "aucune sortie"
            )
        )
        return reponse
    reponse["verifie"] = locale == distante_hex
    if not reponse["verifie"]:
        reponse["ok"] = False
        reponse["error"] = (
            "les empreintes different : le fichier distant est corrompu ou "
            "incomplet. Relance le transfert."
        )
    return reponse

@outil(
    annotations=MUTATING,
    description="Rapatrie un fichier ou un repertoire depuis ROMEO vers la machine locale.",
)
def download_from_romeo(
    remote_path: str, local_path: str, recursive: bool = False, verify: bool = True
) -> dict[str, Any]:
    """Transfert descendant, avec controle d'integrite de bout en bout."""
    s = session()
    try:
        source = check_path(remote_path, s.home, s.scratch, s.path_aliases)
        resultat = files.download(s.host, source, local_path, recursive)
    except (GuardError, SSHError) as exc:
        return _error(str(exc))

    reponse = {"ok": True, **resultat}
    destination = Path(resultat["to"]).expanduser()
    if not verify or recursive or not destination.is_file():
        reponse["verifie"] = False
        return reponse

    try:
        distante = _sh(s, files.commande_empreinte(source), timeout=300)
        locale = files.empreinte_locale(destination)
    except (OSError, SSHError, SSHTimeout) as exc:
        reponse["verifie"] = False
        reponse["avertissement"] = "controle impossible : {}".format(exc)
        return reponse

    distante_hex = files.empreinte_depuis_sortie(distante.stdout) if distante.ok else ""
    reponse["empreinte_locale"] = locale
    reponse["empreinte_distante"] = distante_hex
    if not distante_hex:
        reponse["verifie"] = False
        reponse["avertissement"] = (
            "impossible de lire l'empreinte distante : {}".format(
                distante.stdout.strip()[:200] or "aucune sortie"
            )
        )
        return reponse
    reponse["verifie"] = locale == distante_hex
    if not reponse["verifie"]:
        reponse["ok"] = False
        reponse["error"] = (
            "les empreintes different : le fichier recupere est corrompu ou "
            "incomplet. Relance le transfert."
        )
    return reponse

# =============================================================================
# Stockage
# =============================================================================
@outil(
    annotations=READ_ONLY,
    description=(
        "Repere ce qui occupe le stockage : plus gros repertoires, journaux de "
        "jobs anciens, points de reprise volumineux, environnements virtuels "
        "dupliques. Ne supprime rien ; propose les commandes de menage. A "
        "utiliser quand romeo_quota signale un depassement."
    ),
)
def storage_usage_audit(path: str = "", top: int = 12) -> dict[str, Any]:
    """Inventaire des gros consommateurs d'espace, sans rien effacer."""
    s = session()
    try:
        cible = check_path(path, s.home, s.scratch, s.path_aliases) if path else s.scratch
    except GuardError as exc:
        return _error(str(exc))

    top = max(3, min(int(top), 40))
    q = shlex.quote(cible)
    commande = (
        "echo '###DIRS'; du -x -h --max-depth=2 {q} 2>/dev/null | sort -rh | head -n {n}; "
        "echo '###GROS'; find {q} -xdev -type f -size +200M -printf '%s\\t%p\\n' "
        "2>/dev/null | sort -rn | head -n {n}; "
        "echo '###LOGS'; find {q} -xdev -type f \\( -name '*.out' -o -name '*.err' \\) "
        "-mtime +14 -printf '%s\\t%p\\n' 2>/dev/null | sort -rn | head -n {n}; "
        "echo '###VENVS'; find {q} -xdev -maxdepth 4 -type d -name 'site-packages' "
        "2>/dev/null | head -n {n}; "
        "echo '###CACHES'; du -x -sh {q}/.cache {q}/ia 2>/dev/null"
    ).format(q=q, n=top)

    try:
        resultat = _sh(s, commande, timeout=240, max_chars=20_000)
    except SSHTimeout:
        return _error(
            "l'inventaire a depasse le delai : cible un sous-repertoire precis "
            "avec `path`."
        )
    except SSHError as exc:
        return _error(str(exc))

    sections: dict[str, list[str]] = {}
    courant = None
    for ligne in resultat.stdout.splitlines():
        if ligne.startswith("###"):
            courant = ligne[3:].strip().lower()
            sections[courant] = []
        elif courant and ligne.strip():
            sections[courant].append(ligne.strip())

    def _paires(cle):
        sorties = []
        for ligne in sections.get(cle, []):
            morceaux = ligne.split("\t") if "\t" in ligne else ligne.split(None, 1)
            if len(morceaux) == 2:
                sorties.append({"taille": morceaux[0], "path": morceaux[1]})
        return sorties

    logs = _paires("logs")
    suggestions = []
    if logs:
        suggestions.append(
            "Journaux de plus de 14 jours : "
            "find {} -type f \\( -name '*.out' -o -name '*.err' \\) -mtime +14 "
            "-delete".format(cible)
        )
    if sections.get("venvs"):
        suggestions.append(
            "Plusieurs environnements Python detectes : ils pesent souvent "
            "plusieurs gigaoctets chacun. Supprime ceux qui ne servent plus."
        )
    if sections.get("caches"):
        suggestions.append(
            "Caches IA : leur contenu est reconstructible, tu peux le vider "
            "sans perte."
        )
    suggestions.append(
        "Le serveur ne supprime rien de lui-meme : relis les chemins puis "
        "execute la commande choisie toi-meme."
    )

    return {
        "ok": True,
        "path": cible,
        "repertoires": _paires("dirs"),
        "gros_fichiers": _paires("gros"),
        "journaux_anciens": logs,
        "environnements_python": sections.get("venvs", []),
        "caches": sections.get("caches", []),
        "suggestions": suggestions,
    }

@outil(
    annotations=MUTATING,
    description=(
        "Telecharge un jeu de donnees depuis un noeud de calcul plutot que "
        "depuis le noeud de login, dont la bande passante est partagee. "
        "Accepte une URL directe, un dataset Hugging Face ou un depot git. "
        "Hugging Face exige env_path avec huggingface_hub deja installe via romeo_pip_install ; "
        "ce telechargement n'installe aucun paquet."
    ),
)
def stage_dataset(
    source: str,
    destination: str,
    kind: str = "auto",
    minutes: int = 60,
    time_limit: str | None = None,
    arch: str = "x64cpu",
    env_path: str | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Rapatrie des donnees via un job, pour epargner le noeud de login."""
    s = session()
    if not source.strip():
        return _error("source vide")
    try:
        cible = check_path(destination, s.home, s.scratch, s.path_aliases)
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
        commande = "curl -fL --retry 3 -o {} {}".format(
            shlex.quote(posixpath.join(cible, posixpath.basename(source))),
            shlex.quote(source),
        )
        paquets = ["curl"]
    elif nature == "git":
        commande = "git clone --depth 1 {} {}".format(
            shlex.quote(source), shlex.quote(cible)
        )
        paquets = []
    elif nature == "huggingface":
        if not env_path:
            return _error("Hugging Face requiert env_path, un venv existant contenant huggingface_hub. "
                          "Installe ce paquet explicitement avec romeo_pip_install sur la meme architecture.")
        try:
            environnement = check_path(env_path, s.home, s.scratch, s.path_aliases)
        except GuardError as exc:
            return _error(str(exc))
        python = shlex.quote(posixpath.join(environnement, "bin", "python"))
        # L'API Python publique evite de dependre du chemin interne de la CLI.
        # Le job de telechargement ne lance jamais d'installateur.
        code = ("import sys; from huggingface_hub import snapshot_download; "
                "snapshot_download(repo_id=sys.argv[1], local_dir=sys.argv[2], repo_type='dataset')")
        commande = (
            "{python} -c 'import huggingface_hub' || {{ "
            "echo 'huggingface_hub absent : utilise romeo_pip_install dans ce venv.' >&2; exit 1; }}; "
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
        workdir=cible,
    )
    try:
        spec.workdir = cible
        plan = plan_job(spec, s.scratch)
    except (ClusterError, SSHError, SSHTimeout) as exc:
        return _error(str(exc))

    if not confirm:
        return {
            "ok": True, "submitted": False, "mode": "simulation",
            "kind": nature, "destination": cible, "script": plan.script,
            "next_step": "Rappelle avec confirm=true pour lancer le telechargement.",
        }

    soumission = _soumettre_sbatch(
        s, plan, spec.name, note="staging {}".format(nature)
    )
    if not soumission["ok"]:
        return soumission
    job_id = soumission["job_id"]
    return {
        "ok": True, "submitted": True, "job_id": job_id,
        "kind": nature, "destination": cible,
        "next_step": "Suis le telechargement avec job_status('{}').".format(job_id),
    }

# =============================================================================
# Verification statique d'un script de soumission
# =============================================================================
_MOTIFS_SECRET = re.compile(
    r"(?i)\b(api[_-]?key|token|password|passwd|secret|aws_secret)\b\s*=\s*['\"]?\S{8,}"
)

@outil(
    annotations=READ_ONLY,
    description=(
        "Verifie un script de soumission AVANT de l'envoyer : fins de ligne "
        "Windows qui corrompent l'interpreteur, directives #SBATCH placees trop "
        "tard, `--mem` manquant que ROMEO exige, chemins inexistants, variables "
        "non definies, secrets ecrits en clair. Accepte le texte du script ou "
        "le chemin d'un script deja depose sur le cluster."
    ),
)
def sbatch_lint(script: str = "", path: str = "") -> dict[str, Any]:
    """Analyse statique d'un fichier de soumission."""
    s = session()
    if not script.strip() and not path.strip():
        return _error("fournis `script` (le texte) ou `path` (un fichier distant).")

    origine = "texte fourni"
    if path.strip():
        try:
            cible = check_path(path, s.home, s.scratch, s.path_aliases)
            lecture = _sh(
                s, "cat {} 2>&1".format(shlex.quote(cible)), timeout=45,
                max_chars=200_000,
            )
        except (GuardError, SSHError, SSHTimeout) as exc:
            return _error(str(exc))
        if not lecture.ok:
            return _error(lecture.stdout.strip()[:200] or "fichier illisible")
        script = lecture.stdout
        origine = cible

    constats = []

    def signaler(gravite, message, ligne=None, remede=""):
        constats.append(
            {"gravite": gravite, "message": message, "ligne": ligne, "remede": remede}
        )

    # Les fins de ligne Windows font echouer le shebang de facon opaque :
    # « bad interpreter: /bin/bash^M ».
    if "\r\n" in script or "\r" in script:
        signaler(
            "haute",
            "Le script contient des retours chariot Windows (CRLF). "
            "L'interpreteur lit alors `/bin/bash\\r` et refuse de demarrer.",
            remede="Convertis avec `dos2unix` ou `sed -i 's/\\r$//' <fichier>`.",
        )

    lignes = script.replace("\r\n", "\n").split("\n")
    if not lignes or not lignes[0].startswith("#!"):
        signaler("haute", "Aucune ligne shebang en tete du script.",
                 ligne=1, remede="Commence par `#!/usr/bin/env bash`.")

    # SLURM cesse de lire l'en-tete a la premiere ligne executable.
    premiere_commande = None
    for index, ligne in enumerate(lignes, start=1):
        depouillee = ligne.strip()
        if not depouillee or depouillee.startswith("#"):
            continue
        premiere_commande = index
        break
    for index, ligne in enumerate(lignes, start=1):
        if ligne.strip().startswith("#SBATCH") and premiere_commande and index > premiere_commande:
            signaler(
                "haute",
                "Directive #SBATCH placee apres la premiere commande : SLURM "
                "l'ignore silencieusement.",
                ligne=index,
                remede="Remonte-la dans l'en-tete, avant toute ligne executable.",
            )

    entete = "\n".join(lignes[: premiere_commande or len(lignes)])
    if "--mem" not in entete:
        signaler(
            "haute",
            "Aucune directive `--mem` : ROMEO refuse la soumission avec "
            "« Memory resource is missing ».",
            remede="Ajoute `#SBATCH --mem=<N>G`.",
        )
    if "--account" not in entete:
        signaler("moyenne", "Aucun `--account` : la soumission peut etre refusee.",
                 remede="Ajoute `#SBATCH --account={}`.".format(DEFAULT_ACCOUNT or "VOTRE_PROJET"))
    if "--time" not in entete:
        signaler("moyenne", "Aucun `--time` : la limite par defaut de la "
                 "partition s'applique, souvent trop courte.")

    if _MOTIFS_SECRET.search(script):
        signaler(
            "haute",
            "Une valeur ressemblant a un secret est ecrite en clair dans le "
            "script. Elle serait lisible par quiconque accede au fichier.",
            remede="Depose-la dans un fichier a droits 600 et passe "
                   "`secret_env_file` a job_prepare.",
        )

    if re.search(r"\bmodule\s+load\b", script) and "romeo_load_" not in script:
        signaler(
            "basse",
            "Le script utilise `module load` sans charger l'environnement de "
            "l'architecture. Sur ROMEO 2025, la voie officielle est "
            "`romeo_load_<arch>_env` puis `spack load`.",
        )

    # Chemins absolus mentionnes : on verifie leur existence reelle. Les racines
    # sont **derivees** de la session plutot que figees dans un motif : une liste
    # ecrite en dur rate l'emplacement reel du scratch (chemin physique GPFS) et
    # laisse alors passer sans controle les chemins qui comptent le plus.
    try:
        racines_data = [
            r for r in allowed_roots(s.home, s.scratch, s.path_aliases)
            if r not in ("/tmp", "/apps")
        ]
    except (SSHError, SSHTimeout):
        # Hors ligne : on retombe sur les racines documentees de ROMEO. Le
        # controle d'existence ne tournera pas de toute facon.
        racines_data = ["/home", "/scratch_p", "/gpfs/scratch", "/project",
                        "/gpfs/projet"]
    candidats = {
        m.group(0) for m in re.finditer(r"(?<![\w$])/[\w./-]+", script)
        if "$" not in m.group(0)
    }
    tous_chemins = sorted(
        c for c in candidats
        if any(c == r or c.startswith(r.rstrip("/") + "/") for r in racines_data)
    )
    chemins = tous_chemins[:MAX_CHEMINS_VERIFIES]
    manquants = []
    if chemins:
        try:
            verif = _sh(
                s,
                "; ".join(
                    'test -e {p} || echo "ABSENT {p}"'.format(p=shlex.quote(c))
                    for c in chemins
                ),
                timeout=60,
            )
            manquants = [
                l.split(None, 1)[1] for l in verif.stdout.splitlines()
                if l.startswith("ABSENT ")
            ]
        except (SSHError, SSHTimeout):
            pass
    for absent in manquants:
        signaler("moyenne", "Chemin inexistant sur le cluster : {}".format(absent),
                 remede="Verifie l'orthographe, ou cree-le avant la soumission.")
    if len(tous_chemins) > len(chemins):
        signaler(
            "basse",
            "{} chemins absolus supplementaires n'ont pas ete verifies "
            "({} sur {} controles).".format(
                len(tous_chemins) - len(chemins), len(chemins), len(tous_chemins)),
            remede="Decoupe le script, ou verifie ces chemins avec `list_dir`.",
        )

    # Variables utilisees mais jamais definies dans le script ni connues de SLURM.
    connues = {
        "HOME", "USER", "PATH", "PWD", "TMPDIR", "SHELL", "LD_LIBRARY_PATH",
        "OMP_NUM_THREADS", "CUDA_VISIBLE_DEVICES",
    }
    # `readonly`, `local`, `declare` et `typeset` declarent tout autant
    # qu'`export`. Ne reconnaitre qu'`export` transforme un script rigoureux en
    # pluie de faux signalements : plus l'auteur est discipline, plus le
    # controle est bruyant, et le plafond ci-dessous evince alors les vrais.
    definies = set(re.findall(
        r"^\s*(?:export\s+|readonly\s+|local\s+|typeset\s+"
        r"|declare\s+(?:-\w+\s+)*)?([A-Za-z_]\w*)=", script, re.M))
    definies |= set(re.findall(r"^\s*for\s+([A-Za-z_]\w*)\s+in\b", script, re.M))
    definies |= set(re.findall(r"^\s*read\s+(?:-\w+\s+)*([A-Za-z_]\w*)", script, re.M))
    utilisees = set(re.findall(r"\$\{?([A-Za-z_]\w*)", script))
    # `${VAR:-defaut}`, `${VAR:?message}` et leurs variantes disent
    # explicitement que la variable vient de l'exterieur et que le cas est
    # traite. C'est l'inverse d'un oubli : le signaler serait a contresens.
    traitees = set(re.findall(r"\$\{([A-Za-z_]\w*)\s*:?[-=?+]", script))
    toutes_inconnues = sorted(
        v for v in utilisees - definies - connues - traitees
        if not v.startswith("SLURM") and not v.startswith("_ROMEO")
    )
    inconnues = toutes_inconnues[:MAX_VARIABLES_SIGNALEES]
    for variable in inconnues:
        signaler(
            "basse",
            "Variable `${}` utilisee sans etre definie dans le script.".format(variable),
            remede="Definis-la, ou passe-la par `secret_env_file` si elle est "
                   "sensible.",
        )
    # Tronquer un affichage est acceptable, tronquer un *controle* en silence
    # ne l'est pas : « aucun probleme detecte » deviendrait un mensonge.
    if len(toutes_inconnues) > len(inconnues):
        signaler(
            "basse",
            "{} autres variables potentiellement non definies ne sont pas "
            "listees ({} sur {} affichees).".format(
                len(toutes_inconnues) - len(inconnues),
                len(inconnues), len(toutes_inconnues)),
            remede="Corrige celles ci-dessus puis relance `sbatch_lint`.",
        )

    graves = [c for c in constats if c["gravite"] == "haute"]
    return {
        "ok": True,
        "origine": origine,
        "lignes": len(lignes),
        "constats": constats,
        "bloquants": len(graves),
        "verdict": (
            "{} probleme(s) bloquant(s) : corrige-les avant de soumettre.".format(
                len(graves))
            if graves
            else "Aucun probleme bloquant detecte."
            if constats
            else "Script conforme."
        ),
    }

# =============================================================================
# Audit du scratch
# =============================================================================
@outil(
    annotations=READ_ONLY,
    description=(
        "Repere les fichiers volumineux abandonnes sous le scratch : anciens, "
        "sans job actif associe, ou typiques de fichiers temporaires de calcul "
        "(.rwf, .scr, .tmp). Ne supprime rien. Utile quand romeo_quota signale "
        "un depassement."
    ),
)
def audit_orphan_files(
    path: str = "", days: int = 7, min_size_mb: int = 100, top: int = 20
) -> dict[str, Any]:
    """Inventaire des residus volumineux, croise avec les jobs encore actifs."""
    s = session()
    try:
        cible = check_path(path, s.home, s.scratch, s.path_aliases) if path else s.scratch
    except GuardError as exc:
        return _error(str(exc))

    days = max(1, min(int(days), 365))
    min_size_mb = max(1, min(int(min_size_mb), 100_000))
    top = max(5, min(int(top), 100))
    q = shlex.quote(cible)

    commande = (
        "echo '###ANCIENS'; find {q} -xdev -type f -size +{taille}M -mtime +{jours} "
        "-printf '%s\\t%TY-%Tm-%Td\\t%p\\n' 2>/dev/null | sort -rn | head -n {n}; "
        "echo '###TEMPORAIRES'; find {q} -xdev -type f \\( -name '*.rwf' -o "
        "-name '*.scr' -o -name '*.tmp' -o -name 'core.*' -o -name '*.swp' \\) "
        "-printf '%s\\t%TY-%Tm-%Td\\t%p\\n' 2>/dev/null | sort -rn | head -n {n}; "
        "echo '###JOBDIRS'; find {q} -xdev -maxdepth 1 -type d -name 'job_*' "
        "-printf '%f\\n' 2>/dev/null | head -n 40; "
        "echo '###ACTIFS'; squeue -h -u $USER -o '%i'"
    ).format(q=q, taille=min_size_mb, jours=days, n=top)

    try:
        resultat = _sh(s, commande, timeout=300, max_chars=25_000)
    except SSHTimeout:
        return _error(
            "l'inventaire a depasse le delai : cible un sous-repertoire avec "
            "`path`, ou releve `min_size_mb`."
        )
    except SSHError as exc:
        return _error(str(exc))

    sections: dict[str, list[str]] = {}
    courant = None
    for ligne in resultat.stdout.splitlines():
        if ligne.startswith("###"):
            courant = ligne[3:].strip().lower()
            sections[courant] = []
        elif courant and ligne.strip():
            sections[courant].append(ligne.rstrip())

    def _fichiers(cle):
        sorties = []
        for ligne in sections.get(cle, []):
            morceaux = ligne.split("\t")
            if len(morceaux) == 3:
                sorties.append({
                    "taille_mb": round(int(morceaux[0]) / 1024 / 1024, 1),
                    "modifie": morceaux[1],
                    "path": morceaux[2],
                })
        return sorties

    actifs = {l.strip().split("_")[0] for l in sections.get("actifs", []) if l.strip()}
    # Un `job_<id>` dont l'identifiant n'est plus en file est un residu : son
    # piege de nettoyage n'a pas pu s'executer, typiquement apres un SIGKILL.
    orphelins = [
        d for d in sections.get("jobdirs", [])
        if d.startswith("job_") and d[4:].split("_")[0] not in actifs
    ]

    anciens, temporaires = _fichiers("anciens"), _fichiers("temporaires")
    total_mb = sum(f["taille_mb"] for f in anciens + temporaires)

    suggestions = []
    if orphelins:
        suggestions.append(
            "{} repertoire(s) `job_*` sans job actif : leur piege de nettoyage "
            "n'a pas pu s'executer, typiquement apres un arret brutal. "
            "Verifie puis supprime.".format(len(orphelins))
        )
    if temporaires:
        suggestions.append(
            "{} fichier(s) temporaires de calcul detectes (.rwf, .scr, core...). "
            "Ils ne servent qu'a un job en cours.".format(len(temporaires))
        )
    if anciens:
        suggestions.append(
            "{} fichier(s) de plus de {} Mo non modifies depuis {} jours, soit "
            "{:.1f} Go au total.".format(
                len(anciens), min_size_mb, days,
                sum(f["taille_mb"] for f in anciens) / 1024)
        )
    suggestions.append(
        "Le serveur ne supprime rien : relis les chemins puis efface toi-meme "
        "ce qui doit l'etre."
    )

    return {
        "ok": True, "path": cible, "seuil_jours": days, "seuil_mb": min_size_mb,
        "fichiers_anciens": anciens,
        "fichiers_temporaires": temporaires,
        "repertoires_job_orphelins": orphelins,
        "jobs_actifs": sorted(actifs),
        "total_recuperable_mb": round(total_mb, 1),
        "suggestions": suggestions,
    }

# =============================================================================
# Secrets
# =============================================================================
@outil(
    annotations=MUTATING,
    description=(
        "Cree le dossier et le fichier de secrets sur ROMEO, puis impose les "
        "permissions 700/600. Prepare le stockage des variables sensibles (jetons, mots "
        "de passe) pour les jobs. Les valeurs ne transitent JAMAIS par ce "
        "serveur : tu les ecris toi-meme dans un fichier a droits restreints, "
        "que le job source au demarrage (chemin fourni a job_prepare via `secret_env_file`). Elles "
        "n'apparaissent ainsi ni dans le script sbatch, ni dans le registre "
        "local, ni dans cette conversation."
    ),
)
def secret_env_prepare(name: str = "secrets.env") -> dict[str, Any]:
    """Prepare un fichier de secrets a droits restreints, sans jamais lire son contenu."""
    s = session()
    if name in {".", ".."} or not re.fullmatch(r"[\w.-]{1,64}", name):
        return _error("nom de fichier invalide : {!r}".format(name))

    dossier = posixpath.join(s.home, ".romeo-mcp")
    chemin = posixpath.join(dossier, name)
    try:
        resultat = _sh(
            s,
            "umask 077; mkdir -p {d} && chmod 700 {d} && touch {f} && chmod 600 {f} && "
            "stat -c '%a %n' {f}".format(d=shlex.quote(dossier), f=shlex.quote(chemin)),
            timeout=45,
        )
    except (SSHError, SSHTimeout) as exc:
        return _error(str(exc))
    if not resultat.ok:
        return _error(resultat.stdout.strip()[:200])

    return {
        "ok": True,
        "fichier": chemin,
        "droits": resultat.stdout.strip(),
        "marche_a_suivre": [
            "Connecte-toi a ROMEO et edite ce fichier toi-meme, une ligne par "
            "variable : `MA_CLE=valeur`.",
            "Ne colle jamais la valeur dans cette conversation : elle serait "
            "conservee dans l'historique.",
            "Passe ensuite `secret_env_file='{}'` a job_prepare : le script "
            "sourcera le fichier au demarrage.".format(chemin),
        ],
        "garanties": [
            "Le serveur ne lit jamais le contenu de ce fichier.",
            "Le script sbatch ne contient que le chemin, pas les valeurs.",
            "Le registre local des jobs conserve le script, donc pas davantage.",
            "Le fichier est en droits 600 : lisible par toi seul.",
        ],
    }
