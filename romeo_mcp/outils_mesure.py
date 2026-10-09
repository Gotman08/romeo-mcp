"""Observer un calcul, pendant ou apres.

Diagnostic post-mortem, telemetrie en direct, pile d'appels, profilage,
sante du parc, empreinte energetique.
"""

from __future__ import annotations
from . import workload_preparation
from .plans import submit_prepared

import re
import shlex
from typing import Any, Literal
from .cluster import format_slurm_time, require_account
from .diagnostics import analyser, commande_recherche_checkpoints
from .hardware import (
    analyser_gpu,
    decoder_throttle,
)
from .registry import registry
from .sortie import premiere_ligne
from .slurm import gpus_from_tres, parse_mem_mb
from .ssh import SSHError, SSHTimeout, session
from .outils_calcul import job_efficiency, job_log_tail, job_status
from .noyau import (
    MUTATING,
    READ_ONLY,
    _entier,
    _error,
    _flottant,
    _resumer_tableau,
    _sh,
    _srun_overlap,
    indices_pile,
    outil,
)


# =============================================================================
# Diagnostic post-mortem
# =============================================================================
@outil(
    annotations=READ_ONLY,
    description=(
        "Autopsie d'un job en echec, en un seul appel : etat SLURM, fin des "
        "journaux, causes reconnues et remedes. Reconnait notamment le binaire "
        "x86 execute sur un noeud aarch64, la saturation de VRAM, le "
        "depassement de memoire, l'erreur de bus, les echecs NCCL et les "
        "quotas. En cas de depassement de temps, cherche aussi les points de "
        "reprise disponibles. A appeler des qu'un job echoue, avant toute autre "
        "investigation."
    ),
)
def diagnose_job(job_id: str, lines: int = 80) -> dict[str, Any]:
    """Rassemble en une passe ce qu'un diagnostic manuel demanderait d'aller
    chercher dans trois ou quatre commandes distinctes."""
    s = session()
    jid = str(job_id).strip()
    lines = max(10, min(int(lines), 300))

    etat = job_status(jid)
    if not etat.get("ok"):
        return etat
    if not etat.get("finished"):
        return {
            "ok": True,
            "job_id": jid,
            "en_cours": True,
            "etat": etat.get("state"),
            "message": (
                "Le job n'est pas termine : rien a diagnostiquer pour l'instant. "
                "Suis-le avec job_status, ou consulte sa sortie avec job_log_tail."
            ),
        }

    journaux = job_log_tail(jid, stream="both", lines=lines, max_chars=14_000)
    texte = journaux.get("content", "") if journaux.get("ok") else ""

    limites = {}
    efficacite = job_efficiency(jid)
    if efficacite.get("ok"):
        limites = {
            "memoire_demandee_mb": efficacite.get("req_mem_mb"),
            "memoire_max_atteinte_mb": efficacite.get("max_rss_mb"),
            "efficacite_cpu_pct": efficacite.get("cpu_efficiency_pct"),
            "gpus_alloues": efficacite.get("alloc_gpus"),
            "duration_seconds": efficacite.get("elapsed_seconds"),
        }

    rapport = analyser(
        etat.get("state", ""), etat.get("exit_code", ""), texte, limites
    )
    rapport["ok"] = True
    rapport["job_id"] = jid
    rapport["nom"] = etat.get("name")

    # Un depassement de temps se rattrape par une reprise : autant chercher
    # tout de suite s'il existe un point de sauvegarde exploitable.
    if any(c["cle"] == "temps" for c in rapport["causes"]):
        record = registry().get(jid)
        workdir = record["workdir"] if record else None
        if workdir:
            try:
                trouves = _sh(
                    s, commande_recherche_checkpoints(shlex.quote(workdir)),
                    timeout=60, max_chars=4_000,
                )
                points = []
                for ligne in trouves.stdout.splitlines():
                    morceaux = ligne.split(None, 2)
                    if len(morceaux) >= 2:
                        points.append(morceaux[1])
                rapport["checkpoints"] = points
                rapport["reprise"] = (
                    "Points de reprise trouves : relance avec un temps plus "
                    "large et fais pointer ton script sur le plus recent."
                    if points
                    else "Aucun point de reprise dans le repertoire du job : "
                         "ajoute des sauvegardes periodiques avant de relancer."
                )
            except (SSHError, SSHTimeout):
                pass

    return rapport

@outil(
    annotations=READ_ONLY,
    description=(
        "Telemetrie instantanee d'un job EN COURS, sans lire de journal ni "
        "attendre la fin : occupation et memoire des GPU, temperature, "
        "puissance, et processus les plus actifs. Detecte le cas ou le calcul "
        "dort sur des entrees-sorties pendant que les GPU sont reserves, et la "
        "montee vers la saturation de VRAM avant qu'elle ne provoque un echec."
    ),
)
def job_live_metrics(job_id: str) -> dict[str, Any]:
    """Sonde le materiel d'un job en cours via une etape SLURM superposee."""
    s = session()
    jid = str(job_id).strip()

    etat = job_status(jid)
    if not etat.get("ok"):
        return etat
    if etat.get("finished") or etat.get("state") != "RUNNING":
        return _error(
            "le job {} n'est pas en cours d'execution (etat : {}). La "
            "telemetrie en direct ne s'applique qu'a un job RUNNING ; utilise "
            "job_efficiency pour un job termine.".format(jid, etat.get("state")),
            job_id=jid,
            state=etat.get("state"),
        )

    sonde = (
        "bash -lc "
        + shlex.quote(
            "echo '###GPU'; "
            "nvidia-smi --query-gpu=index,utilization.gpu,utilization.memory,"
            "memory.used,memory.total,temperature.gpu,power.draw "
            "--format=csv,noheader,nounits 2>/dev/null; "
            "echo '###PROC'; "
            "ps -u \"$USER\" -o pid,pcpu,pmem,etime,comm --sort=-pcpu "
            "--no-headers 2>/dev/null | head -6; "
            "echo '###LOAD'; uptime | sed 's/.*load average/load/'"
        )
    )
    try:
        resultat = _srun_overlap(s, jid, sonde)
    except (SSHError, SSHTimeout) as exc:
        return _error(str(exc), job_id=jid)
    if not resultat.ok:
        return _error(
            "la sonde n'a pas pu s'attacher au job : {}".format(
                resultat.stdout.strip()[:300]
            ),
            job_id=jid,
        )

    sections: dict[str, list[str]] = {}
    courant = None
    for ligne in resultat.stdout.splitlines():
        if ligne.startswith("###"):
            courant = ligne[3:].strip().lower()
            sections[courant] = []
        elif courant and ligne.strip():
            sections[courant].append(ligne.strip())

    gpus = []
    for ligne in sections.get("gpu", []):
        champs = [c.strip() for c in ligne.split(",")]
        if len(champs) < 7:
            continue
        try:
            utilisee, totale = float(champs[3]), float(champs[4])
        except ValueError:
            continue
        gpus.append(
            {
                "index": champs[0],
                "utilisation_pct": _entier(champs[1]),
                "utilisation_memoire_pct": _entier(champs[2]),
                "vram_utilisee_mib": _entier(champs[3]),
                "vram_totale_mib": _entier(champs[4]),
                "vram_pct": round(utilisee / totale * 100, 1) if totale else None,
                "temperature_c": _entier(champs[5]),
                "puissance_w": _flottant(champs[6]),
            }
        )

    processus = []
    for ligne in sections.get("proc", []):
        champs = ligne.split(None, 4)
        if len(champs) == 5:
            processus.append(
                {
                    "pid": champs[0], "cpu_pct": champs[1], "mem_pct": champs[2],
                    "duration": champs[3], "commande": champs[4],
                }
            )

    # --- lecture des mesures ------------------------------------------------
    constats = []
    if gpus:
        utilisation = [g["utilisation_pct"] or 0 for g in gpus]
        moyenne = sum(utilisation) / len(utilisation)
        pic_vram = max((g["vram_pct"] or 0) for g in gpus)
        if moyenne < 15:
            constats.append(
                "GPU a {:.0f} % en moyenne alors que le job tourne : le calcul "
                "attend probablement des donnees. Regarde le chargement des "
                "donnees, le nombre de processus de lecture, ou envisage de "
                "mettre le jeu de donnees en memoire vive "
                "(job_prepare(stage_archive=...)).".format(moyenne)
            )
        elif moyenne > 90:
            constats.append(
                "GPU satures a {:.0f} % : le calcul est bien limite par le "
                "GPU, c'est le regime recherche.".format(moyenne)
            )
        if pic_vram > 90:
            constats.append(
                "VRAM a {:.0f} % : la saturation est proche. Reduis la taille "
                "de lot avant que le job n'echoue.".format(pic_vram)
            )
        elif pic_vram < 25 and moyenne > 50:
            constats.append(
                "VRAM utilisee a seulement {:.0f} % : tu peux probablement "
                "augmenter la taille de lot.".format(pic_vram)
            )
        chaud = [g for g in gpus if (g["temperature_c"] or 0) >= 85]
        if chaud:
            constats.append(
                "{} GPU au-dela de 85 degres : surveille un eventuel "
                "ralentissement thermique.".format(len(chaud))
            )
    else:
        constats.append(
            "Aucun GPU visible : job sans GPU, ou pilote inaccessible depuis "
            "l'etape superposee."
        )

    return {
        "ok": True,
        "job_id": jid,
        "node": etat.get("reason_or_nodelist") or etat.get("nodes"),
        "elapsed": etat.get("elapsed"),
        "gpus": gpus,
        "processus": processus,
        "charge": sections.get("load", [""])[0] if sections.get("load") else None,
        "constats": constats,
    }

@outil(
    annotations=READ_ONLY,
    description=(
        "Capture la pile d'appels des processus d'un job EN COURS, pour "
        "diagnostiquer un blocage : interblocage MPI, noyau CUDA fige, attente "
        "sur verrou. Utilise pstack, avec repli sur gdb puis eu-stack. Ne "
        "s'attache pas de maniere interactive : il preleve une trace et rend "
        "la main, ce qui n'interrompt pas le calcul."
    ),
)
def job_stack_trace(job_id: str, process_name: str = "", max_processes: int = 3) -> dict[str, Any]:
    """Preleve une trace de pile sur les processus du job."""
    s = session()
    jid = str(job_id).strip()

    etat = job_status(jid)
    if not etat.get("ok"):
        return etat
    if etat.get("state") != "RUNNING":
        return _error(
            "job {} non actif (etat : {}) : il n'y a pas de pile a "
            "prelever.".format(jid, etat.get("state"))
        )

    motif = (process_name or "").strip()
    if motif and not re.match(r"^[\w.+-]{1,64}$", motif):
        return _error(
            "nom de processus invalide : {!r}. Attendu un nom simple, par "
            "exemple `python3` ou `a.out`.".format(process_name)
        )

    selection = (
        'pgrep -u "$USER" -f {} | head -{}'.format(shlex.quote(motif), max_processes)
        if motif
        else 'ps -u "$USER" -o pid= --sort=-pcpu | head -{}'.format(max_processes)
    )
    corps = (
        'PIDS=$({sel}); '
        'if [ -z "$PIDS" ]; then echo "AUCUN_PROCESSUS"; exit 0; fi; '
        'for pid in $PIDS; do '
        '  echo "###PID $pid $(ps -o comm= -p "$pid" 2>/dev/null)"; '
        '  if command -v pstack >/dev/null; then pstack "$pid" 2>&1 | head -40; '
        '  elif command -v gdb >/dev/null; then '
        '    gdb -p "$pid" -batch -ex "thread apply all bt" 2>&1 | head -40; '
        '  else eu-stack -p "$pid" 2>&1 | head -40; fi; '
        'done'
    ).format(sel=selection)

    try:
        resultat = _srun_overlap(s, jid, "bash -lc " + shlex.quote(corps), timeout=180)
    except (SSHError, SSHTimeout) as exc:
        return _error(str(exc), job_id=jid)

    if "AUCUN_PROCESSUS" in resultat.stdout:
        return _error(
            "aucun processus correspondant sur le noeud. Verifie le nom avec "
            "job_live_metrics, qui liste les processus les plus actifs.",
            job_id=jid,
        )

    traces = []
    courante = None
    for ligne in resultat.stdout.splitlines():
        if ligne.startswith("###PID"):
            morceaux = ligne.split(None, 2)
            courante = {
                "pid": morceaux[1] if len(morceaux) > 1 else "?",
                "commande": morceaux[2] if len(morceaux) > 2 else "",
                "pile": [],
            }
            traces.append(courante)
        elif courante is not None:
            courante["pile"].append(ligne)

    indices = indices_pile(resultat.stdout)

    return {
        "ok": True, "job_id": jid, "processus_traces": len(traces),
        "traces": traces, "indices": indices or ["aucun motif de blocage reconnu"],
    }

# =============================================================================
# Sante systeme d'un job en cours
# =============================================================================
@outil(
    annotations=READ_ONLY,
    description=(
        "Sante systeme d'un job EN COURS, GPU ou non : charge processeur face "
        "aux coeurs reserves, attente d'entrees-sorties, memoire utilisee face "
        "a la reservation. Detecte les trois gaspillages classiques : un code "
        "cense etre parallele qui tourne sur un seul coeur, un calcul qui passe "
        "son temps a attendre le systeme de fichiers, et une reservation "
        "memoire massivement surdimensionnee."
    ),
)
def job_system_health(job_id: str) -> dict[str, Any]:
    """Croise la comptabilite SLURM et une sonde directe sur le noeud."""
    s = session()
    jid = str(job_id).strip()

    etat = job_status(jid)
    if not etat.get("ok"):
        return etat
    if etat.get("state") != "RUNNING":
        return _error(
            "job {} non actif (etat : {}). Pour un job termine, utilise "
            "job_efficiency.".format(jid, etat.get("state"))
        )

    try:
        compta = _sh(
            s,
            "sstat -j {} -a -P -n -o JobID,AveCPU,AveRSS,MaxRSS,AveDiskRead,"
            "AveDiskWrite,NTasks 2>/dev/null | head -5".format(shlex.quote(jid)),
            timeout=45,
        )
        alloc = _sh(
            s,
            "squeue -h -j {} -o '%C|%m|%N'".format(shlex.quote(jid)), timeout=30
        )
    except (SSHError, SSHTimeout) as exc:
        return _error(str(exc))

    coeurs_alloues = memoire_demandee = None
    champs = alloc.stdout.strip().split("|")
    if len(champs) >= 2:
        coeurs_alloues = _entier(champs[0])
        memoire_demandee = champs[1].strip()

    # Charge et attente d'entrees-sorties se lisent sur le noeud, pas dans la
    # comptabilite : `sstat` ne rapporte ni l'un ni l'autre.
    sonde = "bash -lc " + shlex.quote(
        "echo '###LOAD'; cut -d' ' -f1-3 /proc/loadavg; "
        "echo '###IOWAIT'; "
        "grep '^cpu ' /proc/stat | awk '{print $6, $2+$3+$4+$5+$6+$7+$8}'; "
        "echo '###PROC'; ps -u \"$USER\" -o pcpu= --no-headers | "
        "awk '{s+=$1} END {print s+0}'"
    )
    try:
        mesures = _srun_overlap(s, jid, sonde, timeout=120)
    except (SSHError, SSHTimeout) as exc:
        return _error(str(exc), job_id=jid)

    sections: dict[str, list[str]] = {}
    courant = None
    for ligne in mesures.stdout.splitlines():
        if ligne.startswith("###"):
            courant = ligne[3:].strip().lower()
            sections[courant] = []
        elif courant and ligne.strip():
            sections[courant].append(ligne.strip())

    # `sections[cle]` existe des que le marqueur a ete lu, meme si la commande
    # n'a rien produit : le defaut de `.get` ne s'appliquait donc jamais, et
    # l'acces par index levait une IndexError hors de tout garde-fou.
    charge = _flottant((premiere_ligne(sections, "load", "0").split() or ["0"])[0])
    cpu_processus = _flottant(premiere_ligne(sections, "proc", "0")) or 0.0

    iowait_pct = None
    if sections.get("iowait"):
        parties = sections["iowait"][0].split()
        if len(parties) == 2:
            attente, total = _flottant(parties[0]), _flottant(parties[1])
            if attente is not None and total:
                iowait_pct = round(attente / total * 100, 1)

    ligne_compta = next(
        (l for l in compta.stdout.splitlines() if "|" in l), ""
    ).split("|")
    ave_rss = parse_mem_mb(ligne_compta[2]) if len(ligne_compta) > 2 else None
    max_rss = parse_mem_mb(ligne_compta[3]) if len(ligne_compta) > 3 else None
    lecture_disque = parse_mem_mb(ligne_compta[4]) if len(ligne_compta) > 4 else None

    constats = []
    if coeurs_alloues and cpu_processus is not None:
        coeurs_utilises = cpu_processus / 100.0
        taux = coeurs_utilises / coeurs_alloues * 100 if coeurs_alloues else 0
        if taux < 20 and coeurs_alloues > 2:
            constats.append(
                "Environ {:.1f} coeur(s) reellement actif(s) sur {} reserves "
                "({:.0f} %). Un code cense etre parallele tourne peut-etre en "
                "sequentiel : verifie OMP_NUM_THREADS, le nombre de rangs MPI, "
                "ou l'option de parallelisme du programme.".format(
                    coeurs_utilises, coeurs_alloues, taux
                )
            )
        elif taux > 85:
            constats.append(
                "{:.0f} % des coeurs reserves sont actifs : le parallelisme "
                "fonctionne.".format(taux)
            )
    if iowait_pct is not None and iowait_pct > 30:
        constats.append(
            "Le noeud passe {:.0f} % de son temps a attendre les entrees-"
            "sorties : le calcul est limite par le systeme de fichiers. "
            "Envisage un repertoire temporaire local "
            "(job_prepare(job_tmpdir=True)) ou la mise en cache en memoire "
            "vive.".format(iowait_pct)
        )
    if max_rss and memoire_demandee:
        demandee = parse_mem_mb(memoire_demandee.rstrip("n c"))
        if demandee and max_rss / demandee < 0.25:
            constats.append(
                "Memoire utilisee a {:.0f} % de la reservation ({:.0f} Mo sur "
                "{:.0f}) : tu immobilises inutilement de la memoire que "
                "d'autres jobs pourraient utiliser.".format(
                    max_rss / demandee * 100, max_rss, demandee
                )
            )
    if not constats:
        constats.append("Aucun gaspillage manifeste sur les mesures relevees.")

    return {
        "ok": True, "job_id": jid, "node": etat.get("reason_or_nodelist"),
        "elapsed": etat.get("elapsed"),
        "coeurs_alloues": coeurs_alloues,
        "cpu_processus_pct": cpu_processus,
        "charge_noeud": charge,
        "iowait_pct": iowait_pct,
        "memoire_demandee": memoire_demandee,
        "rss_moyenne_mb": round(ave_rss, 1) if ave_rss else None,
        "rss_max_mb": round(max_rss, 1) if max_rss else None,
        "lecture_disque_mb": round(lecture_disque, 1) if lecture_disque else None,
        "constats": constats,
        "note": (
            "La charge du noeud est partagee avec les autres jobs qui s'y "
            "executent ; cpu_processus_pct ne compte que tes processus."
        ),
    }

# =============================================================================
# Profilage GPU
# =============================================================================
@outil(
    annotations=MUTATING,
    description=(
        "Prepare un plan local (24 h), sans soumettre. Profile un calcul GPU avec NVIDIA Nsight Systems et produit un rapport "
        "exploitable, au lieu de laisser deviner pourquoi un code est lent. La "
        "capture est fenetree pour ne pas produire une trace enorme. Lis ensuite "
        "le resume avec profile_report."
    ),
)
def job_profile_prepare(
    command: str,
    name: str = "mcp-profile",
    delay_seconds: int = 60,
    duration_seconds: int = 30,
    warmup_steps: int = 5,
    profile_steps: int = 10,
    time_limit: str = "30m",
    gpus_per_node: int = 1,
    cpus_per_task: int = 16,
    arch: str = "armgpu",
    spack_packages: list[str] | None = None,
    workdir: str | None = None,
) -> dict[str, Any]:
    return workload_preparation.job_profile_prepare(
        command=command, name=name, delay_seconds=delay_seconds,
        duration_seconds=duration_seconds, warmup_steps=warmup_steps, profile_steps=profile_steps,
        time_limit=time_limit, gpus_per_node=gpus_per_node, cpus_per_task=cpus_per_task,
        arch=arch, spack_packages=spack_packages, workdir=workdir,
    )


@outil(annotations=MUTATING, description="Soumet le profilage exact prepare par job_profile_prepare. Exige confirm=true ; rend immediatement un job_id.")
def job_profile_submit(plan_id: str, confirm: bool = False) -> dict[str, Any]:
    return submit_prepared("profile", plan_id, confirm)

@outil(
    annotations=READ_ONLY,
    description=(
        "Resume le rapport de profilage d'un job traite par job_profile_prepare : "
        "repartition entre calcul et transferts memoire, et noyaux les plus "
        "couteux. Condense une sortie nsys de plusieurs centaines de lignes en "
        "quelques constats."
    ),
)
def profile_report(job_id: str, top: int = 5) -> dict[str, Any]:
    """Lit et condense la sortie statistique produite par le job de profilage."""
    sortie = job_log_tail(job_id, stream="out", lines=400, max_chars=40_000)
    if not sortie.get("ok"):
        return sortie
    contenu = sortie.get("content", "")
    if "###PROFIL_STATS" not in contenu:
        return _error(
            "aucune section statistique dans la sortie du job {} : soit il n'a "
            "pas ete lance par job_profile_prepare, soit il n'est pas termine.".format(job_id),
            job_id=job_id,
        )

    lignes = contenu.split("###PROFIL_STATS", 1)[1].splitlines()
    section_noyaux, section_memoire, courante = [], [], None
    for ligne in lignes:
        minuscule = ligne.lower()
        if "gpukernsum" in minuscule or "kernel summary" in minuscule:
            courante = section_noyaux
            continue
        if "gpumemtimesum" in minuscule or "memory operation" in minuscule or "memops" in minuscule:
            courante = section_memoire
            continue
        if courante is not None:
            courante.append(ligne)

    noyaux = _resumer_tableau(section_noyaux, max(1, min(int(top), 15)))
    memoire = _resumer_tableau(section_memoire, 5)

    temps_noyaux = sum(k["temps_total_ns"] for k in noyaux)
    temps_memoire = sum(m["temps_total_ns"] for m in memoire)
    total = temps_noyaux + temps_memoire

    constats = []
    if total:
        part_transfert = temps_memoire / total * 100
        if part_transfert > 30:
            constats.append(
                "Les transferts memoire representent {:.0f} % du temps GPU "
                "observe : le calcul est limite par les mouvements de donnees. "
                "Sur Grace Hopper la memoire est unifiee, donc regarde surtout "
                "les copies explicites que ton code fait encore.".format(part_transfert)
            )
        else:
            constats.append(
                "Les transferts memoire ne pesent que {:.0f} % du temps GPU : "
                "le calcul domine, c'est le regime recherche.".format(part_transfert)
            )
    if noyaux:
        premier = noyaux[0]
        if premier["part_pct"] > 40:
            constats.append(
                "Un seul noyau concentre {:.0f} % du temps ({}) : c'est la "
                "cible d'optimisation evidente.".format(
                    premier["part_pct"], premier["nom"][:60]
                )
            )
        if any("gemm" in k["nom"].lower() or "cutlass" in k["nom"].lower()
               for k in noyaux):
            constats.append(
                "Des noyaux de multiplication matricielle dominent : verifie que "
                "la precision mixte bf16 est active, elle engage les coeurs "
                "tensoriels de Hopper."
            )
    if not noyaux and not memoire:
        constats.append(
            "Aucune ligne exploitable : la fenetre de capture n'a peut-etre "
            "rien intercepte. Augmente duration_seconds ou reduis delay_seconds."
        )

    return {
        "ok": True,
        "job_id": job_id,
        "noyaux_les_plus_couteux": noyaux,
        "operations_memoire": memoire,
        "temps_noyaux_ns": temps_noyaux,
        "temps_memoire_ns": temps_memoire,
        "part_transfert_pct": round(temps_memoire / total * 100, 1) if total else None,
        "constats": constats,
    }

# =============================================================================
# Sante du parc
# =============================================================================
@outil(
    annotations=MUTATING,
    description=(
        "Reserve des ressources GPU via srun et verifie leur sante sur un ou plusieurs noeuds : bridage "
        "thermique ou de puissance, erreurs memoire non corrigees, frequence "
        "anormalement basse. Un noeud degrade ne plante pas, il ralentit tout "
        "un job reparti sans erreur visible. Rend une clause --exclude prete a "
        "l'emploi pour les noeuds suspects. Seul check_type='gpu' est disponible ; NCCL est desactive."
    ),
)
def cluster_gpu_health_run(
    nodes: list[str] | None = None,
    check_type: str = "gpu",
    max_nodes: int = 4,
    minutes: int = 5,
) -> dict[str, Any]:
    """Sonde l'etat materiel de quelques noeuds GPU."""
    genre = (check_type or "gpu").strip().lower()
    if genre != "gpu":
        return _error("Seul check_type='gpu' est disponible. Le mode nccl est desactive : "
                      "aucun benchmark NCCL n'est implemente.")
    account = require_account()
    s = session()

    max_nodes = max(1, min(int(max_nodes), 8))
    # Ce bornage doit precede son usage dans le delai SSH : la valeur brute y
    # etait consommee telle quelle. `minutes=600` faisait attendre dix heures
    # en tenant le verrou de la session, ce qui figeait le serveur entier ;
    # une valeur negative provoquait au contraire un delai deja depasse, qui
    # tuait la session au moment meme ou le srun venait d'etre envoye.
    minutes = max(2, min(int(minutes), 15))
    cibles = [n.strip() for n in (nodes or []) if n.strip()][:max_nodes]
    for cible in cibles:
        if not re.match(r"^romeo-[ac]\d{3}$", cible):
            return _error("nom de noeud invalide : {!r}".format(cible))

    options = [
        "srun", "--account={}".format(account), "--partition=instant",
        "--constraint=armgpu", "--time={}".format(format_slurm_time(minutes * 60)),
        "--ntasks-per-node=1", "--cpus-per-task=4", "--mem=20G",
        "--gpus-per-node=1", "--job-name=mcp-sanity",
    ]
    if cibles:
        options += ["--nodelist={}".format(",".join(cibles)),
                    "--nodes={}".format(len(cibles))]
    else:
        options.append("--nodes=1")

    sonde = (
        'bash -lc '
        + shlex.quote(
            'echo "###NOEUD $(hostname)"; '
            "nvidia-smi --query-gpu=index,clocks_throttle_reasons.active,"
            "ecc.errors.uncorrected.volatile.total,clocks.sm,clocks.max.sm,"
            "utilization.gpu,power.draw,power.limit,temperature.gpu "
            "--format=csv,noheader,nounits"
        )
    )
    try:
        resultat = _sh(s, " ".join(options + [sonde]), timeout=minutes * 60 + 240,
                       max_chars=20_000)
    except SSHTimeout:
        return _error(
            "la sonde n'a pas obtenu d'allocation a temps. Reessaie avec moins "
            "de noeuds, ou quand le parc est moins charge."
        )
    except SSHError as exc:
        return _error(str(exc))

    if not resultat.ok:
        return _error("La sonde GPU a echoue : " + resultat.stdout.strip()[:500])

    par_noeud: dict[str, list[dict]] = {}
    courant = None
    for ligne in resultat.stdout.splitlines():
        if ligne.startswith("###NOEUD"):
            courant = ligne.split(None, 1)[1].strip() if " " in ligne else "?"
            par_noeud.setdefault(courant, [])
            continue
        if courant is None or "," not in ligne:
            continue
        champs = [c.strip() for c in ligne.split(",")]
        if len(champs) < 9:
            continue
        par_noeud[courant].append(
            {
                "index": champs[0],
                "throttle": decoder_throttle(champs[1]),
                "ecc_non_corrigees": _entier(champs[2]),
                "horloge_mhz": _entier(champs[3]),
                "horloge_max_mhz": _entier(champs[4]),
                "utilisation_pct": _entier(champs[5]),
                "puissance_w": _flottant(champs[6]),
                "puissance_max_w": _flottant(champs[7]),
                "temperature_c": _entier(champs[8]),
            }
        )

    if not par_noeud or any(not mesures for mesures in par_noeud.values()):
        return _error("Sonde GPU incomplete : aucune mesure exploitable pour au moins un noeud.",
                      noeuds_sondes=list(par_noeud))

    rapports, suspects = [], []
    for noeud, mesures in par_noeud.items():
        anomalies = []
        for mesure in mesures:
            anomalies += [
                "GPU {} : {}".format(mesure["index"], a) for a in analyser_gpu(mesure)
            ]
        rapports.append(
            {"node": noeud, "gpus": mesures, "anomalies": anomalies,
             "sain": not anomalies}
        )
        if anomalies:
            suspects.append(noeud)

    conclusion = []
    if suspects:
        conclusion.append(
            "{} noeud(s) presentent une anomalie. Ecarte-les de tes prochaines "
            "soumissions.".format(len(suspects))
        )
    else:
        conclusion.append(
            "Les {} noeud(s) sondes sont sains : aucun bridage subi, aucune "
            "erreur memoire.".format(len(par_noeud))
        )

    return {
        "ok": True,
        "type": genre,
        "noeuds_sondes": list(par_noeud),
        "rapports": rapports,
        "noeuds_suspects": suspects,
        "exclude": "--exclude={}".format(",".join(suspects)) if suspects else None,
        "conclusion": conclusion,
    }

# =============================================================================
# Empreinte energetique
# =============================================================================
@outil(
    annotations=READ_ONLY,
    description=(
        "Lit l'energie Slurm du job : un compteur absent/nul reste inconnu. "
        "Une allocation exclusive verifiee est necessaire pour attribuer la mesure au job. "
        "Le carbone est calcule avec un facteur RTE sur la periode du job, ou un facteur "
        "manuel cite ; il reste une estimation des emissions, jamais une mesure de CO2. "
        "estimate_if_unavailable=true active explicitement un modele separe."
    ),
)
def job_energy_footprint(job_id: str, gpu_load_factor: float = 0.6,
                         estimate_if_unavailable: bool = False,
                         carbon_source: Literal["rte", "manual", "none"] = "rte",
                         carbon_intensity_g_kwh: float | None = None,
                         carbon_reference: str = "") -> dict[str, Any]:
    """Mesure observee, modele facultatif et facteur carbone source sont distincts."""
    from .energy import footprint
    # Valider les arguments dans footprint avant la premiere lecture SSH.
    def read(command, **options):
        return _sh(session(), command, **options)
    try:
        return footprint(job_id, read, estimate=estimate_if_unavailable,
                         gpu_load_factor=gpu_load_factor, carbon_source=carbon_source,
                         carbon_intensity=carbon_intensity_g_kwh, carbon_reference=carbon_reference)
    except (SSHError, SSHTimeout) as exc:
        return _error(str(exc))
