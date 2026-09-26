"""Confrontation du modele encode a la realite du cluster.

Tout ce que ce serveur promet -- refuser un job qui resterait en attente,
deriver une partition d'un temps, valider un nombre de noeuds -- repose sur un
**releve fige** : partitions, comptes de noeuds, capacites, plafonds du compte.
Un releve est vrai le jour ou on le fait. Rien, jusqu'ici, ne signalait qu'il
avait cesse de l'etre.

C'est la faiblesse structurelle d'un serveur « correct par construction » : sa
correction a une date de peremption invisible. Une partition redimensionnee, un
quota releve, un noeud retire du parc, et les garde-fous se mettent a refuser
des jobs valides ou -- pire -- a en accepter qui resteront en file.

Ce module interroge SLURM et rend les ecarts. Il ne corrige rien : le modele
reste un choix humain, revu en connaissance de cause.
"""

from __future__ import annotations

from .cluster import (
    ARCHS,
    DEFAULT_ACCOUNT,
    DEFAULT_QOS,
    PARTITIONS,
    USER_MAX_CPUS,
    USER_MAX_GPUS,
    USER_MAX_JOBS,
    ClusterError,
    format_slurm_time,
    parse_duration,
)

#: Separateur de champs de la sonde. Une barre verticale, et non une
#: tabulation : `sinfo -o` **n'interprete pas** `\t` et l'emet litteralement,
#: ce qui rendait tout decoupage silencieusement vide -- le controle de derive
#: concluait alors a une derive generale, sur un cluster parfaitement conforme.
#: Un verificateur qui se trompe sur tout est pire qu'aucun verificateur.
SEP = "|"

#: Sonde unique : une seule commande distante pour toutes les rubriques, plutot
#: qu'un aller-retour SSH par sujet verifie. Chaque ligne vaut
#: `<categorie>|<champs...>`. Elle sort toujours en succes, car une rubrique
#: indisponible est un constat a rapporter, pas une panne de transport.
SONDE = r"""
sinfo -h -o 'PART|%P|%l' 2>/dev/null | sort -u
sinfo -h -o '%P|%f|%D' 2>/dev/null | awk -F'|' '
  { gsub(/\*$/, "", $1); split($2, f, ",");
    for (i in f) n[$1 "|" f[i]] += $3 }
  END { for (k in n) printf "NODES|%s|%d\n", k, n[k] }'
sinfo -h -o '%f|%c|%m|%G' 2>/dev/null | sort -u | sed 's/^/ARCH|/'
sacctmgr -nP show assoc user="$(id -un)" format=Account,QOS,GrpTRES,MaxSubmit 2>/dev/null | sed 's/^/ASSOC|/'
if command -v seff >/dev/null 2>&1; then printf 'TOOL|seff|present\n'; else printf 'TOOL|seff|absent\n'; fi
exit 0
"""


def _lignes(brut: str) -> list[list[str]]:
    """Decoupe la sortie de la sonde en champs, lignes vides ignorees."""
    return [
        [champ.strip() for champ in ligne.split(SEP)]
        for ligne in brut.splitlines()
        if ligne.strip()
    ]


def _ecart(rubrique: str, sujet: str, attendu, observe, portee: str) -> dict:
    """Un ecart constate, redige pour etre agi et non seulement lu.

    `portee` dit ce que l'ecart casse concretement. Sans elle, une liste de
    differences chiffrees laisse au lecteur le soin de deviner lesquelles
    comptent, et toutes finissent par etre ignorees.
    """
    return {
        "rubrique": rubrique,
        "sujet": sujet,
        "attendu": attendu,
        "observe": observe,
        "portee": portee,
    }


def _verifier_partitions(champs: list[list[str]], ecarts: list[dict]) -> int:
    """Existence et limite de temps de chaque partition du modele."""
    observees: dict[str, str] = {}
    for ligne in champs:
        if ligne[0] == "PART" and len(ligne) >= 3:
            observees[ligne[1].rstrip("*")] = ligne[2]

    if not observees:
        # Ne rien avoir observe n'autorise aucune conclusion : signaler « toutes
        # les partitions ont disparu » serait un faux massif.
        ecarts.append(_ecart(
            "partition", "releve", "sinfo exploitable", "aucune ligne lue",
            "impossible de conclure sur la derive : verifie que `sinfo` "
            "repond sur le noeud de login.",
        ))
        return 0

    controles = 0
    for nom, modele in PARTITIONS.items():
        controles += 1
        if nom not in observees:
            ecarts.append(_ecart(
                "partition", nom, "existe", "absente de sinfo",
                "toute deduction de partition depuis un temps demande devient "
                "fausse : les jobs seront refuses par SLURM apres coup.",
            ))
            continue
        try:
            reelle = parse_duration(observees[nom])
        except ClusterError:
            continue  # `infinite` ou format inattendu : pas un ecart mesurable
        if reelle != modele["max_seconds"]:
            ecarts.append(_ecart(
                "partition", nom,
                format_slurm_time(modele["max_seconds"]),
                format_slurm_time(reelle),
                "le serveur refusera des durees desormais valides, ou en "
                "laissera passer que SLURM rejettera.",
            ))
    for nom in observees:
        if nom not in PARTITIONS:
            ecarts.append(_ecart(
                "partition", nom, "inconnue du modele", "existe sur le cluster",
                "cette partition ne sera jamais proposee, meme si elle est la "
                "plus adaptee a une demande.",
            ))
    return controles


def _verifier_noeuds(champs: list[list[str]], ecarts: list[dict]) -> int:
    """Comptes de noeuds par partition et par architecture."""
    observes: dict[tuple[str, str], int] = {}
    for ligne in champs:
        if ligne[0] == "NODES" and len(ligne) >= 4:
            try:
                observes[(ligne[1].rstrip("*"), ligne[2])] = int(ligne[3])
            except ValueError:
                continue
    if not observes:
        return 0

    controles = 0
    for nom, modele in PARTITIONS.items():
        for arch, attendu in modele.get("nodes_by_arch", {}).items():
            reel = observes.get((nom, arch))
            if reel is None:
                continue
            controles += 1
            if reel != attendu:
                ecarts.append(_ecart(
                    "noeuds", "{}/{}".format(nom, arch), attendu, reel,
                    "un job demandant plus de noeuds que la partition n'en "
                    "expose reste en file indefiniment ; c'est precisement ce "
                    "que la validation par partition doit empecher.",
                ))
    return controles


def _verifier_architectures(champs: list[list[str]], ecarts: list[dict]) -> int:
    """Capacites reelles d'un noeud de chaque famille."""
    observees: dict[str, list[str]] = {}
    for ligne in champs:
        if ligne[0] == "ARCH" and len(ligne) >= 5:
            for feature in ligne[1].split(","):
                if feature in ARCHS:
                    observees[feature] = ligne[2:5]
    if not observees:
        return 0

    controles = 0
    for arch, modele in ARCHS.items():
        mesure = observees.get(arch)
        if not mesure:
            ecarts.append(_ecart(
                "architecture", arch, "presente",
                "aucun noeud ne porte ce feature",
                "les jobs vises sur cette architecture ne seront jamais places.",
            ))
            continue
        cpus_txt, mem_txt, gres = mesure

        controles += 1
        if cpus_txt.isdigit() and int(cpus_txt) != modele["cpus_per_node"]:
            ecarts.append(_ecart(
                "architecture", "{} coeurs/noeud".format(arch),
                modele["cpus_per_node"], int(cpus_txt),
                "la validation du nombre de coeurs et la part de memoire "
                "derivee des coeurs reposent toutes deux sur cette valeur.",
            ))

        # `sinfo` suffixe d'un `+` les valeurs heterogenes au sein d'un meme
        # feature. Le modele retient alors volontairement la valeur basse :
        # comparer dans ce cas produirait un faux ecart permanent.
        controles += 1
        base = mem_txt.rstrip("+")
        if (base.isdigit() and not mem_txt.endswith("+")
                and int(base) != modele["mem_mb_per_node"]):
            ecarts.append(_ecart(
                "architecture", "{} memoire/noeud (Mo)".format(arch),
                modele["mem_mb_per_node"], int(base),
                "la memoire derivee des coeurs demandes serait mal calibree, "
                "donc rejetee par SLURM ou inutilement large.",
            ))

        controles += 1
        attendus = modele.get("gpus_per_node", 0)
        reels, modele_gpu = _lire_gres(gres)
        if reels != attendus:
            ecarts.append(_ecart(
                "architecture", "{} GPU/noeud".format(arch), attendus, reels,
                "un job demandant plus de GPU qu'un noeud n'en porte est "
                "refuse par SLURM.",
            ))
        if modele_gpu and modele.get("gpu_model") and modele_gpu != modele["gpu_model"]:
            ecarts.append(_ecart(
                "architecture", "{} identifiant GRES".format(arch),
                modele["gpu_model"], modele_gpu,
                "un `--gres=gpu:<modele>` ecrit avec l'ancien identifiant ne "
                "correspondrait plus a aucune ressource.",
            ))
    return controles


def _lire_gres(gres: str) -> tuple[int, str]:
    """Extrait (nombre de GPU, identifiant GRES) d'un champ `%G` de sinfo.

    Le champ vaut `(null)` sans GPU, et `gpu:h100:4` ou `gpu:h100:4(S:0-1)`
    sinon -- le suffixe entre parentheses decrit l'affinite aux sockets.
    """
    if not gres or gres in ("(null)", "N/A"):
        return 0, ""
    # Le suffixe d'affinite contient lui-meme un deux-points (`(S:0-1)`) : le
    # retirer d'abord, sinon le decoupage rend `0-1)` comme quantite de GPU.
    utile = gres.split("(")[0]
    morceaux = utile.split(":")
    identifiant = morceaux[1] if len(morceaux) >= 3 else ""
    quantite = morceaux[-1]
    return (int(quantite) if quantite.isdigit() else 0), identifiant


def _verifier_compte(champs: list[list[str]], ecarts: list[dict]) -> int:
    """Compte facture, QOS et plafonds de l'association SLURM."""
    associations = [l for l in champs if l[0] == "ASSOC" and len(l) >= 5]
    if not associations:
        return 0

    comptes = {l[1] for l in associations if l[1]}
    controles = 1
    if DEFAULT_ACCOUNT not in comptes:
        ecarts.append(_ecart(
            "compte", DEFAULT_ACCOUNT, "association existante",
            ", ".join(sorted(comptes)) or "aucune",
            "Configurer un projet autorise avec `python -m romeo_mcp configure --account VOTRE_PROJET`.",
        ))

    ligne = next((l for l in associations if l[1] == DEFAULT_ACCOUNT), associations[0])
    qos, grptres, maxsubmit = ligne[2], ligne[3], ligne[4]

    controles += 1
    if DEFAULT_QOS and qos and DEFAULT_QOS not in qos.split(","):
        ecarts.append(_ecart(
            "compte", "QOS", DEFAULT_QOS, qos,
            "SLURM refusera la soumission avec une QOS non accordee.",
        ))

    plafonds: dict[str, int] = {}
    for morceau in (grptres or "").split(","):
        cle, _, valeur = morceau.partition("=")
        if valeur.strip().isdigit():
            plafonds[cle.strip()] = int(valeur)

    for cle, attendu, etiquette in (
        ("cpu", USER_MAX_CPUS, "coeurs"),
        ("gres/gpu", USER_MAX_GPUS, "GPU"),
    ):
        if attendu > 0 and cle in plafonds:
            controles += 1
            if plafonds[cle] != attendu:
                ecarts.append(_ecart(
                    "compte", "plafond {}".format(etiquette), attendu, plafonds[cle],
                    "les avertissements de depassement portent alors sur la "
                    "mauvaise valeur : ils arrivent trop tot, ou jamais.",
                ))
    if USER_MAX_JOBS > 0 and maxsubmit.isdigit():
        controles += 1
        if int(maxsubmit) != USER_MAX_JOBS:
            ecarts.append(_ecart(
                "compte", "jobs simultanes", USER_MAX_JOBS, int(maxsubmit),
                "un balayage parametrique pourrait etre refuse en bloc.",
            ))
    return controles


def _verifier_outils(champs: list[list[str]], ecarts: list[dict]) -> int:
    """Outils dont le modele affirme l'absence."""
    for ligne in champs:
        if ligne[0] == "TOOL" and len(ligne) >= 3 and ligne[1] == "seff":
            if ligne[2] == "present":
                ecarts.append(_ecart(
                    "outils", "seff", "absent", "present",
                    "`job_efficiency` recalcule laborieusement depuis `sacct` "
                    "ce que `seff` donnerait directement.",
                ))
            return 1
    return 0


def analyser_releve(brut: str, racines: dict[str, list[str]]) -> dict:
    """Compare le releve brut au modele encode et rend les ecarts.

    Fonction pure : aucun acces reseau, donc testable sans cluster -- ce qu'on
    reproche precisement au reste du serveur de ne pas etre.
    """
    champs = _lignes(brut)
    ecarts: list[dict] = []
    controles = sum((
        _verifier_partitions(champs, ecarts),
        _verifier_noeuds(champs, ecarts),
        _verifier_architectures(champs, ecarts),
        _verifier_compte(champs, ecarts),
        _verifier_outils(champs, ecarts),
    ))

    return {
        "ok": True,
        "conforme": not ecarts,
        "controles": controles,
        "ecarts": ecarts,
        "racines": racines,
        "resume": (
            "modele conforme au cluster sur {} points verifies.".format(controles)
            if not ecarts else
            "{} ecart(s) entre le modele encode et le cluster, sur {} points "
            "verifies. Tant que le modele n'est pas mis a jour, les garde-fous "
            "concernes raisonnent sur des valeurs perimees.".format(
                len(ecarts), controles)
        ),
    }
