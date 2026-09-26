"""Enchainements de jobs : validation du graphe de dependances.

Le serveur savait deja soumettre un job isole, un balayage parametrique
(`submit_array_job`) et une chaine de segments reprenables
(`submit_resilient_job`). Il ne savait pas exprimer la forme la plus courante
d'un calcul serieux : *preparer, calculer, rassembler*, chaque etape n'ayant de
sens qu'apres la precedente.

Faute d'outil, cet enchainement s'ecrit a la main avec des `--dependency`, ce
qui ramene toutes les erreurs que ce serveur existe pour eviter -- et en ajoute
une : une etape dont l'architecture est deduite isolement part sur x86_64 alors
que les autres tournent en aarch64. Declarer l'architecture **une fois pour
l'enchainement** supprime la classe entiere, sans coder en dur le moindre motif
de calcul.

Ce module ne contient que la partie sans reseau -- validation et ordre -- pour
qu'elle soit testable sans cluster.
"""

from __future__ import annotations

from .cluster import ClusterError

#: Champs qu'une etape peut porter. Tout le reste vient de l'enchainement ou
#: des defauts de `submit_job` : une etape decrit une intention de calcul, pas
#: un en-tete sbatch.
CHAMPS_ETAPE = {
    "name", "command", "time_limit", "nodes", "ntasks_per_node",
    "cpus_per_task", "gpus_per_node", "mem_gb", "arch", "partition",
    "modules", "spack_packages", "array", "distributed", "container",
    "redirect_caches", "job_tmpdir", "depends_on", "condition",
}

#: Conditions de dependance SLURM utiles ici. `afterok` est le defaut : une
#: etape de rassemblement n'a aucun sens si le calcul a echoue. `afterany`
#: existe pour les etapes de diagnostic, qui veulent justement s'executer
#: apres un echec.
CONDITIONS = {
    "afterok": "l'etape precedente doit avoir reussi",
    "afterany": "l'etape precedente doit avoir fini, reussie ou non",
    "afternotok": "l'etape precedente doit avoir echoue",
}


def valider_etapes(etapes: list[dict]) -> list[dict]:
    """Verifie la forme de chaque etape et rend une copie normalisee."""
    if not etapes:
        raise ClusterError(
            "enchainement vide : fournis au moins une etape dans `stages`."
        )
    if len(etapes) > 32:
        raise ClusterError(
            "{} etapes demandees : au-dela de 32, il s'agit probablement d'un "
            "balayage parametrique. Utilise submit_array_job, qui n'occupe "
            "qu'une entree de file.".format(len(etapes))
        )

    vues: set[str] = set()
    normalisees = []
    for rang, brute in enumerate(etapes):
        if not isinstance(brute, dict):
            raise ClusterError(
                "etape {} : un objet est attendu, pas {}.".format(
                    rang, type(brute).__name__)
            )
        inconnus = set(brute) - CHAMPS_ETAPE
        if inconnus:
            raise ClusterError(
                "etape {} : champs inconnus {}. Champs acceptes : {}.".format(
                    brute.get("name", rang), sorted(inconnus),
                    ", ".join(sorted(CHAMPS_ETAPE)))
            )
        nom = str(brute.get("name") or "").strip()
        if not nom:
            raise ClusterError("etape {} : `name` est obligatoire.".format(rang))
        if nom in vues:
            raise ClusterError(
                "deux etapes portent le nom {!r}. Les noms servent a exprimer "
                "les dependances : ils doivent etre uniques.".format(nom)
            )
        vues.add(nom)
        if not str(brute.get("command") or "").strip():
            raise ClusterError("etape {!r} : `command` est obligatoire.".format(nom))

        condition = str(brute.get("condition") or "afterok").strip()
        if condition not in CONDITIONS:
            raise ClusterError(
                "etape {!r} : condition {!r} inconnue. Valeurs acceptees : "
                "{}.".format(nom, condition, ", ".join(sorted(CONDITIONS)))
            )
        etape = dict(brute)
        etape["name"] = nom
        etape["condition"] = condition
        etape["depends_on"] = [
            str(d).strip() for d in (brute.get("depends_on") or []) if str(d).strip()
        ]
        normalisees.append(etape)
    return normalisees


def ordonner(etapes: list[dict]) -> list[dict]:
    """Trie les etapes pour qu'une dependance precede toujours son dependant.

    Un tri topologique, avec deux refus explicites : une dependance vers une
    etape qui n'existe pas, et un cycle. Les deux produiraient sinon des jobs
    qui n'ont **aucune chance** de demarrer -- SLURM les accepte et les laisse
    en file pour toujours, ce qui est le pire des echecs : silencieux.
    """
    connues = {e["name"] for e in etapes}
    for etape in etapes:
        for dep in etape["depends_on"]:
            if dep not in connues:
                raise ClusterError(
                    "etape {!r} : dependance vers {!r}, qui n'est pas une etape "
                    "de cet enchainement. Etapes declarees : {}.".format(
                        etape["name"], dep, ", ".join(sorted(connues)))
                )
            if dep == etape["name"]:
                raise ClusterError(
                    "etape {!r} depend d'elle-meme.".format(etape["name"])
                )

    restantes = {e["name"]: set(e["depends_on"]) for e in etapes}
    par_nom = {e["name"]: e for e in etapes}
    ordre: list[dict] = []
    while restantes:
        # On conserve l'ordre de declaration entre etapes egales : le resultat
        # est ainsi reproductible, et lisible par qui a ecrit la demande.
        pretes = [e["name"] for e in etapes
                  if e["name"] in restantes and not restantes[e["name"]]]
        if not pretes:
            raise ClusterError(
                "cycle de dependances entre les etapes {}. Un cycle laisse tous "
                "les jobs concernes en file indefiniment.".format(
                    ", ".join(sorted(restantes)))
            )
        for nom in pretes:
            ordre.append(par_nom[nom])
            del restantes[nom]
            for attentes in restantes.values():
                attentes.discard(nom)
    return ordre


def heriter(etape: dict, defauts: dict) -> dict:
    """Complete une etape par les valeurs declarees pour l'enchainement.

    L'heritage porte sur ce qui doit rester **coherent d'un bout a l'autre** :
    l'architecture avant tout. Une etape peut toujours surcharger, mais elle le
    fait alors explicitement, ce qui se lit dans la demande.
    """
    fusion = dict(etape)
    for cle, valeur in defauts.items():
        if valeur is not None and fusion.get(cle) is None:
            fusion[cle] = valeur
    return fusion


def clause_dependance(etape: dict, identifiants: dict[str, str]) -> str:
    """Clause `--dependency` d'une etape, ou chaine vide si elle n'en a pas."""
    if not etape["depends_on"]:
        return ""
    cibles = ":".join(identifiants[d] for d in etape["depends_on"])
    return "--dependency={}:{}".format(etape["condition"], cibles)
