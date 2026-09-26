"""Sante materielle des GPU et modele energetique.

Deux besoins distincts sont traites ici.

**Reperer un noeud degrade.** Un GPU bride thermiquement ou par la puissance ne
plante pas : il ralentit, et divise le debit de tout un job reparti sans qu'aucune
erreur n'apparaisse. `nvidia-smi` expose la raison du bridage sous forme de champ
de bits, que ce module traduit.

**Estimer l'energie.** ROMEO n'active aucun greffon de comptabilite energetique
(`AcctGatherEnergyType = (null)`, verifie le 2026-08-20), et `ConsumedEnergyRaw`
vaut donc zero sur tous les jobs. Toute empreinte annoncee est un **modele**, pas
une mesure : les fonctions ci-dessous le rendent explicite plutot que de laisser
croire a un releve.
"""

from __future__ import annotations

import os

#: Champ de bits `clocks_throttle_reasons.active` de nvidia-smi.
#: `grave` distingue un bridage subi d'un etat de fonctionnement normal.
RAISONS_THROTTLE: dict[int, tuple[str, bool]] = {
    0x0001: ("GPU au repos", False),
    0x0002: ("frequence applicative imposee", False),
    0x0004: ("plafond de puissance logiciel atteint", False),
    0x0008: ("ralentissement materiel", True),
    0x0010: ("synchronisation de frequence entre GPU", False),
    0x0020: ("ralentissement thermique logiciel", True),
    0x0040: ("ralentissement thermique materiel", True),
    0x0080: ("limitation par frein de puissance", True),
    0x0100: ("frequence d'affichage imposee", False),
}

#: Limite de puissance d'un module GH200, relevee par nvidia-smi.
PUISSANCE_GPU_MAX_W = 900.0

#: Puissance par coeur, faute de mesure : ordres de grandeur assumes.
PUISSANCE_COEUR_W = {"armgpu": 3.5, "x64cpu": 2.5}

#: Intensite carbone du mix electrique francais, en gCO2e par kWh.
#: Surchargeable : elle varie fortement selon l'heure et la saison.
INTENSITE_CARBONE_G_KWH = float(os.environ.get("ROMEO_CARBONE_G_KWH", "56"))


def decoder_throttle(valeur: str) -> list[dict]:
    """Traduit le champ de bits de bridage en raisons lisibles."""
    texte = (valeur or "").strip()
    if not texte or texte.lower() in ("n/a", "[n/a]", "not supported"):
        return []
    try:
        bits = int(texte, 16) if texte.lower().startswith("0x") else int(texte)
    except ValueError:
        return []

    raisons = []
    for masque, (libelle, grave) in RAISONS_THROTTLE.items():
        if bits & masque:
            raisons.append({"libelle": libelle, "preoccupant": grave})
    return raisons


def analyser_gpu(mesure: dict) -> list[str]:
    """Rend les anomalies d'un GPU, ou une liste vide s'il est sain."""
    anomalies = []

    for raison in mesure.get("throttle", []):
        if raison["preoccupant"]:
            anomalies.append(
                "bridage subi : {}".format(raison["libelle"])
            )

    ecc = mesure.get("ecc_non_corrigees")
    if ecc:
        anomalies.append(
            "{} erreur(s) memoire non corrigee(s) : ce GPU est suspect, "
            "signale-le a l'equipe ROMEO".format(ecc)
        )

    horloge, maximum = mesure.get("horloge_mhz"), mesure.get("horloge_max_mhz")
    charge = mesure.get("utilisation_pct")
    # Une frequence basse au repos est normale ; sous charge, elle ne l'est pas.
    if horloge and maximum and charge and charge > 50 and horloge < maximum * 0.6:
        anomalies.append(
            "frequence a {} MHz pour {} MHz possibles alors que le GPU est "
            "charge a {} % : ralentissement anormal".format(horloge, maximum, charge)
        )

    return anomalies


def estimer_energie(
    gpus: int,
    coeurs: int,
    secondes: float,
    arch: str = "armgpu",
    puissance_gpu_mesuree: float | None = None,
    facteur_charge: float = 0.6,
) -> dict:
    """Modelise la consommation d'un job, faute de compteur disponible.

    Quand la puissance GPU a pu etre relevee sur le job en cours, elle est
    utilisee telle quelle. Sinon on applique un facteur de charge a la limite
    du module, et le resultat est encadre par une fourchette : annoncer un
    chiffre unique donnerait une fausse impression de mesure.
    """
    heures = max(0.0, secondes) / 3600.0
    par_coeur = PUISSANCE_COEUR_W.get(arch, 2.5)

    mesuree = puissance_gpu_mesuree is not None
    if mesuree:
        puissance_gpu = puissance_gpu_mesuree * gpus
        basse = haute = puissance_gpu
    else:
        puissance_gpu = PUISSANCE_GPU_MAX_W * facteur_charge * gpus
        basse = PUISSANCE_GPU_MAX_W * 0.25 * gpus
        haute = PUISSANCE_GPU_MAX_W * 0.95 * gpus

    puissance_cpu = par_coeur * coeurs

    def _kwh(watts_gpu):
        return (watts_gpu + puissance_cpu) * heures / 1000.0

    centrale = _kwh(puissance_gpu)
    return {
        # Deux drapeaux plutot qu'un seul, ambigu. L'ENERGIE n'est jamais
        # mesuree ici : ROMEO n'expose aucun compteur. La PUISSANCE GPU, elle,
        # peut avoir ete relevee sur le job en cours, ce qui resserre
        # fortement l'estimation sans pour autant la transformer en mesure.
        # Un unique `mesure_reelle` figé a False contredisait
        # `puissance_gpu_source` dans la meme reponse.
        "mesure_reelle": False,
        "puissance_gpu_mesuree": mesuree,
        "puissance_gpu_source": (
            "relevee sur le job en cours" if mesuree
            else "modelisee a {:.0f} % de la limite de {:.0f} W".format(
                facteur_charge * 100, PUISSANCE_GPU_MAX_W
            )
        ),
        "duree_heures": round(heures, 3),
        "puissance_gpu_w": round(puissance_gpu, 1),
        "puissance_cpu_w": round(puissance_cpu, 1),
        "energie_kwh": round(centrale, 3),
        "energie_kwh_fourchette": [round(_kwh(basse), 3), round(_kwh(haute), 3)],
        "intensite_carbone_g_kwh": INTENSITE_CARBONE_G_KWH,
        "co2e_g": round(centrale * INTENSITE_CARBONE_G_KWH, 1),
        "co2e_g_fourchette": [
            round(_kwh(basse) * INTENSITE_CARBONE_G_KWH, 1),
            round(_kwh(haute) * INTENSITE_CARBONE_G_KWH, 1),
        ],
        "hypotheses": [
            "ROMEO n'active aucun greffon de comptabilite energetique SLURM : "
            "ConsumedEnergyRaw vaut zero, ces chiffres sont donc un modele et "
            "non un releve.",
            "Puissance CPU estimee a {} W par coeur sur {}.".format(par_coeur, arch),
            "Intensite carbone de {} gCO2e/kWh (mix francais moyen) ; elle varie "
            "du simple au triple selon l'heure et la saison.".format(
                INTENSITE_CARBONE_G_KWH
            ),
            "La consommation du refroidissement et du reseau n'est pas comptee : "
            "le total reel du centre est superieur.",
        ],
    }
