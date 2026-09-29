"""Adaptateurs SSH/Slurm et contexte de chemins, sans dependance MCP."""
from __future__ import annotations
import os
import posixpath
import re
import shlex
import time
import uuid
import hashlib
from .cluster import ClusterError, parse_duration
from .ssh import SSHError, SSHTimeout, session
from .registry import registry
from .validation import blocking_problems as _controle_du_script_genere
SEUIL_SESSION_LONGUE = 120
FENETRE_DOUBLON_SECONDES = 900
ETATS_ACTIFS = {"PENDING", "RUNNING", "CONFIGURING", "SUSPENDED", "SUBMITTED", "soumis"}

def _sh(session_obj, command: str, **kwargs):
    """Execute une commande distante, sur la session adaptee a sa duree.

    Le choix est fait ici plutot qu'a chaque appel : c'est l'unique point de
    passage vers le transport, et le delai demande dit deja tout ce qu'il faut
    savoir pour trancher.
    """
    if kwargs.get("timeout", 30) >= SEUIL_SESSION_LONGUE:
        session_obj = session(longue=True)
    return session_obj.run(command, **kwargs)


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
    s, plan, nom: str, *, note: str = "", options: tuple = (), ecrire: bool = True,
    script_path: str | None = None, artifacts: dict | None = None,
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
    # Un nom de job peut etre reutilise pendant qu'une autre soumission est
    # encore en cours. Son script doit donc avoir sa propre adresse.
    if not ecrire and not script_path:
        return _error("le chemin du script existant est requis pour le reutiliser.")
    chemin_script = script_path or posixpath.join(
        plan.workdir, "{}-{}.sbatch".format(nom, uuid.uuid4().hex))
    try:
        if ecrire:
            s.write_file(chemin_script, plan.script, mode="700")
        from .reproducibility import submission_provenance
        from .privacy import sanitize
        provenance = submission_provenance(s, plan)
        provenance["artifacts"] = sanitize({
            **(artifacts or {}),
            "script": {"path": chemin_script, "source": "generated_content",
                       "sha256": hashlib.sha256(plan.script.encode("utf-8")).hexdigest()},
        })
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
