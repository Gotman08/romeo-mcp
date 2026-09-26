"""Enchainements de jobs et controle de derive du modele : sans acces reseau.

Les deux modules testes ici sont volontairement purs -- ils recoivent un releve
ou une liste d'etapes et rendent un verdict -- precisement pour que leur logique
soit exercable sans cluster.
"""

from commun import bilan, check
from commun import expect_error as _expect_error
import offline  # valeurs fictives, aucun acces reseau
from romeo_mcp import pipeline, verification
from romeo_mcp.cluster import ClusterError


def expect_error(label, fn, needle=""):
    """Restreint le harnais aux erreurs du domaine."""
    return _expect_error(label, fn, needle, exceptions=(ClusterError,))


# =============================================================================
# Controle de derive
# =============================================================================
#: Releve fidele au modele encode, tel que ROMEO le rend le 2026-08-21.
RELEVE = """PART|instant*|1:00:00
PART|short|1-00:00:00
PART|long|30-00:00:00
NODES|instant|armgpu|58
NODES|instant|x64cpu|44
NODES|short|armgpu|56
NODES|short|x64cpu|43
NODES|long|armgpu|40
NODES|long|x64cpu|24
ARCH|armgpu|288|820802|gpu:h100:4
ARCH|x64cpu|192|1160629+|(null)
ASSOC|test-project|normal|cpu=1024,gres/gpu=16|80
TOOL|seff|absent"""


def ecarts(releve):
    """Rubriques et sujets des ecarts constates, pour comparaison compacte."""
    return {(e["rubrique"], e["sujet"]) for e in
            verification.analyser_releve(releve, {})["ecarts"]}


print("\n-- derive : le releve fidele ne doit rien signaler --")
_fidele = verification.analyser_releve(RELEVE, {})
check("conforme", _fidele["conforme"] is True, _fidele["ecarts"])
check("au moins 20 points verifies", _fidele["controles"] >= 20, _fidele["controles"])

print("\n-- derive : chaque changement reel doit etre vu --")
# Le cas qui justifie l'outil : une partition retrecie laisse un job accepte
# par le serveur en file pour toujours.
check("partition retrecie",
      ("noeuds", "long/armgpu") in ecarts(RELEVE.replace("NODES|long|armgpu|40",
                                                         "NODES|long|armgpu|25")))
check("limite de temps modifiee",
      ("partition", "short") in ecarts(RELEVE.replace("PART|short|1-00:00:00",
                                                      "PART|short|2-00:00:00")))
check("plafond de compte releve",
      ("compte", "plafond GPU") in ecarts(RELEVE.replace("gres/gpu=16", "gres/gpu=120")))
check("materiel GPU remplace",
      {("architecture", "armgpu GPU/noeud"),
       ("architecture", "armgpu identifiant GRES")} <= ecarts(
          RELEVE.replace("gpu:h100:4", "gpu:b200:8")))
check("coeurs par noeud modifies",
      ("architecture", "armgpu coeurs/noeud") in ecarts(
          RELEVE.replace("ARCH|armgpu|288|", "ARCH|armgpu|144|")))
check("outil declare absent devenu present",
      ("outils", "seff") in ecarts(RELEVE.replace("TOOL|seff|absent",
                                                  "TOOL|seff|present")))
check("partition inconnue du modele",
      ("partition", "gpu-prio") in ecarts(RELEVE + "\nPART|gpu-prio|4:00:00"))

print("\n-- derive : ne pas conclure a partir de rien --")
# Un verificateur qui signale « tout a disparu » des que la sonde se tait est
# pire qu'aucun verificateur : il apprend a ignorer ses propres alertes.
_muet = verification.analyser_releve("", {})
check("sonde muette : un seul constat, sur le releve lui-meme",
      len(_muet["ecarts"]) == 1 and _muet["ecarts"][0]["sujet"] == "releve",
      _muet["ecarts"])
check("sonde muette : aucune partition declaree disparue",
      not any(e["observe"] == "absente de sinfo" for e in _muet["ecarts"]))
# `sinfo` suffixe d'un `+` les valeurs heterogenes : le modele retient la
# valeur basse, comparer produirait un faux ecart a chaque appel.
check("memoire heterogene (suffixe +) : pas un ecart",
      ("architecture", "x64cpu memoire/noeud (Mo)") not in ecarts(RELEVE))

print("\n-- derive : lecture du champ GRES --")
check("(null) vaut zero GPU", verification._lire_gres("(null)") == (0, ""))
check("gpu:h100:4", verification._lire_gres("gpu:h100:4") == (4, "h100"))
check("affinite socket ignoree",
      verification._lire_gres("gpu:h100:4(S:0-1)") == (4, "h100"))


# =============================================================================
# Enchainements de jobs
# =============================================================================
def ordre(etapes):
    return [e["name"] for e in pipeline.ordonner(pipeline.valider_etapes(etapes))]


print("\n-- enchainements : ordre topologique --")
check("dependance avant dependant",
      ordre([{"name": "b", "command": "x", "depends_on": ["a"]},
             {"name": "a", "command": "x"}]) == ["a", "b"])
check("ordre de declaration conserve entre egaux",
      ordre([{"name": "a", "command": "x"}, {"name": "b", "command": "x"},
             {"name": "c", "command": "x", "depends_on": ["a", "b"]}])
      == ["a", "b", "c"])
check("losange",
      ordre([{"name": "fin", "command": "x", "depends_on": ["g", "d"]},
             {"name": "d", "command": "x", "depends_on": ["debut"]},
             {"name": "g", "command": "x", "depends_on": ["debut"]},
             {"name": "debut", "command": "x"}])[0] == "debut")

print("\n-- enchainements : ce qui doit etre refuse --")
# Un cycle ou une dependance fantome produit des jobs que SLURM accepte et
# laisse en file indefiniment : l'echec le plus couteux, parce qu'il est muet.
expect_error("cycle",
             lambda: ordre([{"name": "a", "command": "x", "depends_on": ["b"]},
                            {"name": "b", "command": "x", "depends_on": ["a"]}]),
             "cycle")
expect_error("dependance inexistante",
             lambda: ordre([{"name": "a", "command": "x", "depends_on": ["nulle"]}]),
             "pas une etape")
expect_error("auto-dependance",
             lambda: ordre([{"name": "a", "command": "x", "depends_on": ["a"]}]),
             "elle-meme")
expect_error("noms en double",
             lambda: ordre([{"name": "a", "command": "x"},
                            {"name": "a", "command": "y"}]),
             "unique")
expect_error("commande manquante",
             lambda: ordre([{"name": "a", "command": "  "}]), "command")
expect_error("nom manquant", lambda: ordre([{"command": "x"}]), "name")
expect_error("champ inconnu",
             lambda: ordre([{"name": "a", "command": "x", "gpu": 4}]), "inconnus")
expect_error("condition inconnue",
             lambda: ordre([{"name": "a", "command": "x", "condition": "apres"}]),
             "condition")
expect_error("liste vide", lambda: ordre([]), "vide")
expect_error("etape non-objet", lambda: ordre(["a"]), "objet")
expect_error("trop d'etapes",
             lambda: ordre([{"name": "e{}".format(i), "command": "x"}
                            for i in range(40)]),
             "submit_array_job")

print("\n-- enchainements : heritage --")
# Le point de l'heritage : une etape sans GPU d'un enchainement aarch64 ne doit
# pas partir seule sur x86_64.
check("architecture heritee",
      pipeline.heriter({"name": "post", "command": "x"},
                       {"arch": "armgpu"})["arch"] == "armgpu")
check("surcharge explicite respectee",
      pipeline.heriter({"name": "post", "command": "x", "arch": "x64cpu"},
                       {"arch": "armgpu"})["arch"] == "x64cpu")
check("valeur nulle n'ecrase rien",
      "arch" not in pipeline.heriter({"name": "p", "command": "x"}, {"arch": None}))

print("\n-- enchainements : clause de dependance --")
_etapes = pipeline.valider_etapes([
    {"name": "a", "command": "x"},
    {"name": "b", "command": "x", "depends_on": ["a"]},
    {"name": "c", "command": "x", "depends_on": ["a", "b"], "condition": "afterany"},
])
_ids = {"a": "101", "b": "102"}
check("sans dependance : clause vide",
      pipeline.clause_dependance(_etapes[0], _ids) == "")
check("afterok par defaut",
      pipeline.clause_dependance(_etapes[1], _ids) == "--dependency=afterok:101")
check("dependances multiples et condition explicite",
      pipeline.clause_dependance(_etapes[2], _ids) == "--dependency=afterany:101:102")

raise SystemExit(bilan("AJOUTS"))
