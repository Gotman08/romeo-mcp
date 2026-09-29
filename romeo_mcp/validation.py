"""Validation pure de scripts Slurm, utilisable sans MCP ni SSH."""
import re
from .cluster import DEFAULT_ACCOUNT
MAX_VARIABLES_SIGNALEES = 8
_MOTIFS_SECRET = re.compile(r"(?i)\b(api[_-]?key|token|password|passwd|secret|aws_secret)\b\s*=\s*['\"]?\S{8,}")

def validate_script(script: str) -> dict:
    if not script.strip():
        return {"ok": False, "error": "script vide"}
    origine = "texte fourni (analyse locale)"
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
            remede="Corrige celles ci-dessus puis relance `sbatch_validate`.",
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


def blocking_problems(script: str) -> list[str]:
    report = validate_script(script)
    if not report["ok"]:
        return [report["error"]]
    return [c["message"] for c in report["constats"] if c["gravite"] == "haute"]
