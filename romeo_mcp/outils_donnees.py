"""Fichiers, stockage, secrets, et verification statique des scripts.

Tout ce qui touche au contenu depose sur le cluster plutot qu'aux calculs.
"""

from __future__ import annotations
from . import workload_preparation

import posixpath
import json
import re
import shlex
from typing import Annotated, Any
from pathlib import Path
from pydantic import Field
from . import files
from .remote_reads import LIST_DIRECTORY, READ_TEXT
from .validation import validate_script
from .file_operations import check_script_paths, create_file, replace_file
from .plans import submit_prepared
from .guard import GuardError, check_path
from .ssh import SSHError, SSHTimeout, session
from .noyau import MUTATING, DESTRUCTIVE, READ_ONLY, _error, _sh, outil


# =============================================================================
# Fichiers
# =============================================================================
CharacterBudget = Annotated[int, Field(strict=True, ge=1, le=64_000)]


def _read_json(result):
    """Ne jamais transformer une sonde incomplete en observation valide."""
    if result.truncated:
        raise ValueError("reponse de lecture distante incomplete : budget de transport depasse")
    try:
        payload = json.loads(result.stdout)
    except ValueError as exc:
        raise ValueError("reponse de lecture distante invalide") from exc
    if not isinstance(payload, dict):
        raise ValueError("reponse de lecture distante invalide")
    return payload


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
        result = _sh(
            s,
            "python3 -c {} {} {}".format(shlex.quote(LIST_DIRECTORY), shlex.quote(target), limit),
            timeout=40,
            # 255 octets par nom POSIX, au plus six caracteres JSON par octet,
            # plus les metadonnees. Aucun texte humain n'est decoupe.
            max_chars=limit * (255 * 6 + 512) + 1024,
            read_only=True,
        )
    except (SSHError, SSHTimeout) as exc:
        return _error(str(exc))
    if not result.ok:
        return _error(
            "repertoire introuvable ou illisible : {}".format(target),
            path=target,
            detail=result.stdout.strip()[:200],
        )

    payload = _read_json(result)
    entries = payload.get("entries")
    if not isinstance(entries, list) or len(entries) > limit or type(payload.get("truncated")) is not bool:
        return _error("liste distante invalide", path=target)
    return {"ok": True, "path": target, "count": len(entries), **payload}

@outil(
    annotations=READ_ONLY,
    description=(
        "Lit une tranche d'un fichier distant. Toujours borne : precise offset "
        "et limit plutot que de rapatrier un fichier entier."
    ),
)
def read_remote_file(
    path: str, offset: int = 1, limit: int = 200, max_chars: CharacterBudget = 8000
) -> dict[str, Any]:
    """Lit `limit` lignes a partir de la ligne `offset` (1-indexee)."""
    if type(max_chars) is not int or not 1 <= max_chars <= 64_000:
        return _error("max_chars doit etre un entier compris entre 1 et 64000.")
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
            "python3 -c {} {} {} {} {}".format(
                shlex.quote(READ_TEXT), shlex.quote(target), offset, limit, max_chars
            ),
            timeout=45,
            # Un caractere Unicode hors BMP occupe douze caracteres en JSON
            # ASCII. La capture est bornee meme pour une tres longue ligne.
            max_chars=12 * (max_chars + 1) + 1024,
            read_only=True,
        )
    except (SSHError, SSHTimeout) as exc:
        return _error(str(exc))
    if not result.ok:
        return _error(result.stdout.strip() or "fichier illisible", path=target)

    payload = _read_json(result)
    content, truncated = payload.get("content"), payload.get("truncated")
    if not isinstance(content, str) or len(content) > max_chars or type(truncated) is not bool:
        return _error("tranche distante invalide", path=target)

    return {
        "ok": True,
        "path": target,
        "offset": offset,
        "limit": limit,
        "total_lines": payload.get("total_lines"),
        "truncated": truncated,
        "content": content,
    }

@outil(annotations=MUTATING, description=(
    "Cree un fichier texte sur ROMEO. Refuse toute cible existante, y compris un lien symbolique. "
    "Le repertoire parent doit exister ; publication atomique du contenu, permissions 600."))
def file_create(path: str, content: str) -> dict[str, Any]:
    return create_file(session(), path, content)


@outil(annotations=DESTRUCTIVE, description=(
    "Remplace explicitement le contenu d'un fichier regulier existant sur ROMEO, sans suivre les liens symboliques. "
    "expected_sha256 facultatif refuse un contenu modifie depuis sa lecture. Publication atomique ; permissions conservees. "
    "Le verrou coordonne les ecritures de ces outils ; les autres programmes doivent respecter ce verrou."))
def file_replace(path: str, content: str, expected_sha256: str | None = None) -> dict[str, Any]:
    return replace_file(session(), path, content, expected_sha256)

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
        "Prepare un plan local de telechargement (24 h), sans soumission ni ecriture sur ROMEO. Telecharge un jeu de donnees depuis un noeud de calcul plutot que "
        "depuis le noeud de login, dont la bande passante est partagee. "
        "Accepte une URL directe, un dataset Hugging Face ou un depot git. "
        "Hugging Face exige env_path avec huggingface_hub deja installe via python_packages_install ; "
        "ce telechargement n'installe aucun paquet."
    ),
)
def dataset_prepare(
    source: str,
    destination: str,
    kind: str = "auto",
    minutes: int = 60,
    time_limit: str | None = None,
    arch: str = "x64cpu",
    env_path: str | None = None,
) -> dict[str, Any]:
    return workload_preparation.dataset_prepare(
        source=source, destination=destination, kind=kind,
        minutes=minutes, time_limit=time_limit, arch=arch,
        env_path=env_path,
    )


@outil(annotations=MUTATING, description="Soumet le telechargement exact prepare par dataset_prepare. Exige confirm=true ; rend immediatement un job_id.")
def dataset_download(plan_id: str, confirm: bool = False) -> dict[str, Any]:
    return submit_prepared("dataset", plan_id, confirm)

# =============================================================================
# Verification statique d'un script de soumission
# =============================================================================
@outil(annotations=READ_ONLY, description=(
    "Analyse uniquement le texte du script Slurm : syntaxe des directives, ressources, variables et secrets. "
    "Aucun acces SSH ni lecture de fichier. Utilise sbatch_check_paths pour verifier les chemins distants."))
def sbatch_validate(script: str) -> dict[str, Any]:
    return validate_script(script)


@outil(annotations=READ_ONLY, description=(
    "Verifie sur ROMEO, par SSH, les chemins absolus litteraux du texte fourni. "
    "Ne valide pas la syntaxe du script. Les chemins dynamiques ne sont pas resolus ; aucun fichier n'est cree."))
def sbatch_check_paths(script: str) -> dict[str, Any]:
    return check_script_paths(session(), script)

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
