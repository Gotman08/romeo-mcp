"""Tests unitaires des charges de travail : diagnostic, lanceurs, gabarits.

Couvre le cas courant du cluster (MPI, jobs scalaires) autant que les
options propres a PyTorch, aux conteneurs et aux caches Python, dont on
verifie surtout qu elles restent inactives par defaut.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from commun import bilan, check  # noqa: E402
import offline  # valeurs fictives, aucun acces reseau
from romeo_mcp import diagnostics, templates  # noqa: E402
from romeo_mcp.cluster import ClusterError  # noqa: E402
from romeo_mcp.slurm import JobSpec, plan_job  # noqa: E402

SCRATCH = "/scratch_p/moi"


def cles(rapport):
    return [c["cle"] for c in rapport["causes"]]


print("\n-- reconnaissance des modes d'echec --")
CAS = [
    ("architecture", "COMPLETED", "bash: ./monbinaire: Illegal instruction (core dumped)"),
    ("architecture", "FAILED", "cannot execute binary file: Exec format error"),
    ("capacite_cuda", "FAILED", "CUDA error: no kernel image is available for execution"),
    ("memoire_gpu", "FAILED",
     "torch.cuda.OutOfMemoryError: CUDA out of memory. Tried to allocate 2.00 GiB"),
    ("memoire_vive", "FAILED",
     "slurmstepd: error: Detected 1 oom-kill event(s) in StepId=42.batch"),
    ("memoire_partagee", "FAILED", "DataLoader worker (pid 123) is killed by signal: Bus error"),
    ("communication_gpu", "FAILED",
     "romeo-a012:31:31 [0] NCCL WARN Connect to 10.0.0.4<45231> failed : ncclSystemError"),
    ("quota", "FAILED", "OSError: [Errno 122] Disk quota exceeded: '/home/moi/x.pt'"),
    ("module_python", "FAILED", "ModuleNotFoundError: No module named 'torch'"),
    ("bibliotheque", "FAILED",
     "error while loading shared libraries: libcudart.so.12: cannot open shared object file"),
    ("permission", "FAILED", "PermissionError: [Errno 13] Permission denied"),
]
for attendu, etat, journal in CAS:
    rapport = diagnostics.analyser(etat, "1:0", journal)
    check("detecte {}".format(attendu), attendu in cles(rapport), cles(rapport))
    if attendu in cles(rapport):
        cause = next(c for c in rapport["causes"] if c["cle"] == attendu)
        check("  {} a des remedes".format(attendu), len(cause["remedes"]) >= 1)
        check("  {} cite sa preuve".format(attendu), bool(cause["preuve"]))

print("\n-- etats SLURM porteurs de sens --")
r = diagnostics.analyser("TIMEOUT", "0:0", "")
check("TIMEOUT reconnu", "temps" in cles(r), cles(r))
check("TIMEOUT conseille la reprise", any("reprise" in x or "sauvegarde" in x
                                          for x in r["causes"][0]["remedes"]))
r = diagnostics.analyser("OUT_OF_MEMORY", "0:125", "")
check("OUT_OF_MEMORY reconnu", "memoire_vive" in cles(r))
r = diagnostics.analyser("NODE_FAIL", "0:0", "")
check("NODE_FAIL reconnu", "noeud" in cles(r))

print("\n-- absence de faux positifs --")
r = diagnostics.analyser("COMPLETED", "0:0", "Epoch 3/3 : loss 0.21\nTermine proprement.")
check("journal sain -> aucune cause", r["causes"] == [], cles(r))
check("journal sain -> indice fourni", "indice" in r)

print("\n-- priorite architecture sur le bruit --")
melange = ("ModuleNotFoundError: No module named 'torch'\n"
           "Illegal instruction (core dumped)\n")
r = diagnostics.analyser("FAILED", "132:0", melange)
check("les deux causes sont remontees",
      {"architecture", "module_python"} <= set(cles(r)), cles(r))
check("architecture citee en premier", cles(r)[0] == "architecture", cles(r))

print("\n-- caches Python (optionnels) --")
lignes = templates.exports_caches(SCRATCH)
texte = "\n".join(lignes)
for variable in ("HF_HOME", "TORCH_HOME", "TRITON_CACHE_DIR", "WANDB_DIR",
                 "XDG_CACHE_HOME", "UV_CACHE_DIR"):
    check("cache {} redirige".format(variable), variable in texte)
check("caches hors du home", "/scratch_p/moi" in texte and "$HOME" not in texte)
check("repertoires crees", "mkdir -p" in texte)

print("\n-- preambule distribue --")
p = "\n".join(templates.preambule_distribue("ddp", 4, nccl_debug=True))
check("MASTER_ADDR depuis le premier noeud",
      'scontrol show hostnames "$SLURM_JOB_NODELIST"' in p and "head -n 1" in p)
check("MASTER_PORT defini", "MASTER_PORT" in p)
check("WORLD_SIZE calcule", "WORLD_SIZE" in p)
check("NCCL_DEBUG sur demande", "NCCL_DEBUG=INFO" in p)
check("NCCL_DEBUG absent sinon",
      "NCCL_DEBUG" not in "\n".join(templates.preambule_distribue("ddp", 4, False)))
p_srun = "\n".join(templates.preambule_distribue("deepspeed", 4, False))
check("rangs SLURM pour deepspeed",
      "SLURM_PROCID" in p_srun and "SLURM_LOCALID" in p_srun)

print("\n-- lanceurs --")
check("ddp utilise torchrun",
      "torchrun" in templates.lanceur_distribue("ddp", "t.py", 4))
check("ddp passe par srun",
      templates.lanceur_distribue("ddp", "t.py", 4).startswith("srun "))
check("accelerate utilise son lanceur",
      "accelerate launch" in templates.lanceur_distribue("accelerate", "t.py", 4))
check("deepspeed passe par srun simple",
      templates.lanceur_distribue("deepspeed", "t.py", 4) == "srun t.py")

print("\n-- conteneur --")
c = templates.enveloppe_conteneur("/img/ngc.sif", "python t.py", ["/scratch_p/moi"])
check("apptainer exec", c.startswith("apptainer exec"))
check("--nv present (sinon aucun GPU visible)", "--nv" in c)
check("montage applique", "--bind /scratch_p/moi" in c)

print("\n-- tunnel --")
t = templates.commande_tunnel("romeo", "romeo-a041", 2345, 8888)
check("forme documentee", t == "ssh -N -L 8888:romeo-a041:2345 romeo", t)

print("\n-- integration dans le script sbatch --")
# ntasks_per_node=4 est volontairement incorrect pour ddp : torchrun deploie
# lui-meme un processus par GPU, donc le serveur doit ramener la valeur a 1.
plan = plan_job(
    JobSpec(name="ia", command="train.py", time="2h", nodes=2, gpus_per_node=4,
            ntasks_per_node=4, cpus_per_task=32, distributed="ddp"), SCRATCH)
check("caches non injectes par defaut", "HF_HOME" not in plan.script)
check("rendez-vous injecte", "MASTER_ADDR" in plan.script)
check("torchrun injecte", "torchrun" in plan.script)
check("une tache par noeud pour ddp", plan.spec.ntasks_per_node == 1)
check("topologie corrigee et signalee",
      any("ntasks_per_node" in w for w in plan.warnings), plan.warnings)
check("directive sbatch coherente", "--ntasks-per-node=1" in plan.script)
check("pas d'avertissement MPI redondant",
      not any("ni srun ni mpirun" in w for w in plan.warnings))

plan_ds = plan_job(
    JobSpec(name="ds", command="train.py", time="1h", gpus_per_node=4,
            cpus_per_task=16, distributed="deepspeed"), SCRATCH)
check("une tache par GPU pour deepspeed", plan_ds.spec.ntasks_per_node == 4)
check("rangs SLURM presents", "SLURM_PROCID" in plan_ds.script)

plan_avec = plan_job(JobSpec(name="py", command="t.py", time="30m",
                             redirect_caches=True), SCRATCH)
check("caches activables a la demande", "HF_HOME" in plan_avec.script)

plan_c = plan_job(
    JobSpec(name="cont", command="python t.py", time="1h", gpus_per_node=1,
            container="/img/ngc.sif"), SCRATCH)
check("conteneur injecte", "apptainer exec --nv" in plan_c.script)
check("montages par defaut", "--bind /scratch_p/moi" in plan_c.script)
check("avertissement image arm64",
      any("arm64" in w for w in plan_c.warnings), plan_c.warnings)

print("\n-- refus coherents --")
for label, kwargs, motif in [
    ("famille inconnue", dict(distributed="horovod", gpus_per_node=1), "inconnue"),
    ("distribue sans GPU", dict(distributed="ddp", gpus_per_node=0), "au moins un GPU"),
]:
    try:
        plan_job(JobSpec(name="x", command="a", time="1h", **kwargs), SCRATCH)
        check(label, False, "aucune erreur")
    except ClusterError as exc:
        check(label, motif in str(exc), str(exc))

print("\n-- recherche de points de reprise --")
cmd = diagnostics.commande_recherche_checkpoints("/scratch_p/moi/run")
check("cible le repertoire", "/scratch_p/moi/run" in cmd)
check("cherche les extensions usuelles", ".ckpt" in cmd and ".safetensors" in cmd)
check("resultat borne", "head -8" in cmd)

print("\n-- mise en cache en memoire vive --")
stg = "\n".join(templates.preambule_staging_shm("/scratch_p/moi/data.tar"))
check("repertoire propre au job", "/dev/shm/$SLURM_JOB_ID" in stg)
check("nettoyage enfile, non pose en trap propre",
      "_ROMEO_NETTOYAGE+=" in stg and "trap " not in stg)
check("archive extraite", "tar -xf" in stg)
check("variable exportee", "export DATASET_DIR=" in stg)
check("limite reelle documentee", "239" in stg and "partage" in stg)

print("\n-- enveloppe reprenable --")
res = "\n".join(templates.enveloppe_resiliente("python t.py", "/ckpt", 300))
check("marqueur de fin court-circuite le segment", 'if [ -f "$CHECKPOINT_DIR/TERMINE" ]' in res)
check("piege SIGUSR1 installe", "trap _sauvegarde_demandee SIGUSR1" in res)
check("signal relaye a l'application", 'kill -USR1 "$APP_PID"' in res)
check("temoin de sauvegarde depose", "SAUVEGARDE_DEMANDEE" in res)
# La commande est enveloppee dans une fonction avant d'etre mise en
# arriere-plan : c'est ce qui la rend insensible au nombre de lignes.
check("application enveloppee puis mise en arriere-plan",
      "python t.py" in res and "_romeo_charge &" in res)
check("attente reprise apres signal", '[ "$CODE" -gt 128 ]' in res)
check("marqueur pose si succes", 'touch "$CHECKPOINT_DIR/TERMINE"' in res)
check("code de sortie propage", 'exit "$CODE"' in res)

print("\n-- integration sbatch : signal et reprise --")
pr = plan_job(
    JobSpec(name="chaine", command="python t.py", time="1h", gpus_per_node=1,
            cpus_per_task=16, checkpoint_dir="/scratch_p/moi/ckpt",
            signal_before=300, stage_archive="/scratch_p/moi/d.tar",
            redirect_caches=False), SCRATCH)
check("directive de preavis", "#SBATCH --signal=B:SIGUSR1@300" in pr.script)
check("preavis vise le script de lot", "B:SIGUSR1" in pr.script)
check("staging present", "/dev/shm/$SLURM_JOB_ID" in pr.script)
check("enveloppe presente", "trap _sauvegarde_demandee SIGUSR1" in pr.script)
check("rien apres le exit final", pr.script.rstrip().endswith('exit "$CODE"'),
      pr.script.rstrip()[-40:])

sans = plan_job(JobSpec(name="simple", command="echo ok", time="30m",
                        redirect_caches=False), SCRATCH)
check("pas de directive de signal sans reprise", "--signal" not in sans.script)
check("job simple termine par sa trace",
      sans.script.rstrip().endswith('echo "[romeo-mcp] fin $(date -Is)"'))

print("\n-- lecture des piles d'appels --")
from romeo_mcp.server import indices_pile  # noqa: E402

# Non-regression : `execute_command_internal` contient « cu » et faisait
# conclure a tort a un blocage CUDA quand la casse etait ignoree.
check("bash sans faux positif CUDA",
      indices_pile("#3 0x00 in execute_command_internal ()") == [],
      indices_pile("#3 0x00 in execute_command_internal ()"))
check("appel pilote camelCase reconnu",
      any("CUDA" in i for i in indices_pile("#1 in cuLaunchKernel () from libcuda.so")))
check("nccl reconnu", any("CUDA" in i for i in indices_pile("ncclAllReduce ()")))
check("mpi reconnu", any("MPI" in i for i in indices_pile("#2 in PMPI_Barrier ()")))
check("verrou reconnu", any("verrou" in i for i in indices_pile("in pthread_cond_wait ()")))
check("entree-sortie reconnue",
      any("entree-sortie" in i for i in indices_pile("#0 in read () from libc.so.6")))
check("pile anodine sans indice", indices_pile("#0 in time_sleep ()") == [])

print("\n-- greffe de staging sur script existant --")
from romeo_mcp.server import inject_io_staging  # noqa: E402

modele = ("#!/usr/bin/env bash\n#SBATCH --job-name=x\n#SBATCH --mem=50G\n\n"
          "module purge\npython t.py\n")
inj = inject_io_staging(modele, "/scratch_p/moi/d.tar")
check("greffe acceptee", inj.get("ok") is True, inj.get("error"))
lignes_inj = inj["script"].splitlines()
i_dernier_sbatch = max(i for i, l in enumerate(lignes_inj) if l.startswith("#SBATCH"))
i_stage = next(i for i, l in enumerate(lignes_inj) if "STAGE_DIR=" in l)
i_corps = next(i for i, l in enumerate(lignes_inj) if l.startswith("module purge"))
check("insere apres la derniere directive", i_dernier_sbatch < i_stage)
check("insere avant le corps du script", i_stage < i_corps)
check("rappels fournis", len(inj.get("rappels", [])) >= 3)
check("script sans directive refuse", not inject_io_staging("echo x", "/d.tar").get("ok"))
check("archive vide refusee", not inject_io_staging(modele, "  ").get("ok"))
check("chemin suspect refuse",
      not inject_io_staging(modele, "/d.tar; rm -rf /").get("ok"))

print("\n-- decodage du bridage GPU --")
from romeo_mcp import hardware  # noqa: E402

check("repos non preoccupant",
      hardware.decoder_throttle("0x0000000000000001") ==
      [{"libelle": "GPU au repos", "preoccupant": False}])
graves = hardware.decoder_throttle("0x48")
check("bits combines decodes", len(graves) == 2, graves)
check("thermique signale preoccupant", all(r["preoccupant"] for r in graves))
check("champ vide tolere", hardware.decoder_throttle("") == [])
check("valeur non numerique toleree", hardware.decoder_throttle("[N/A]") == [])
check("decimal accepte", len(hardware.decoder_throttle("1")) == 1)

print("\n-- analyse de sante GPU --")
sain = {"throttle": hardware.decoder_throttle("0x1"), "ecc_non_corrigees": 0,
        "horloge_mhz": 345, "horloge_max_mhz": 1980, "utilisation_pct": 0}
check("GPU au repos declare sain", hardware.analyser_gpu(sain) == [],
      hardware.analyser_gpu(sain))
# Frequence basse au repos : normal. Sous charge : anormal.
charge_lente = dict(sain, utilisation_pct=95, horloge_mhz=800)
check("frequence basse sous charge signalee",
      any("anormal" in a for a in hardware.analyser_gpu(charge_lente)))
check("erreurs ECC signalees",
      any("memoire non corrigee" in a
          for a in hardware.analyser_gpu(dict(sain, ecc_non_corrigees=2))))
check("bridage thermique signale",
      any("bridage subi" in a for a in hardware.analyser_gpu(
          dict(sain, throttle=hardware.decoder_throttle("0x40")))))

print("\n-- modele energetique --")
e = hardware.estimer_energie(gpus=4, coeurs=64, secondes=3600, arch="armgpu", intensite_carbone_g_kwh=25)
check("jamais presente comme une mesure", e["mesure_reelle"] is False)
check("fourchette encadrant la valeur",
      e["energie_kwh_fourchette"][0] <= e["energie_kwh"] <= e["energie_kwh_fourchette"][1],
      (e["energie_kwh_fourchette"], e["energie_kwh"]))
check("hypotheses explicitees", len(e["hypotheses"]) >= 3)
check("modele et absence de mesure explicites",
      any("aucune energie mesuree" in h for h in e["hypotheses"]))
check("carbone derive de l'energie",
      abs(e["co2e_g"] - e["energie_kwh"] * e["intensite_carbone_g_kwh"]) < 0.5)
mesure = hardware.estimer_energie(gpus=2, coeurs=32, secondes=3600,
                                  puissance_gpu_mesuree=450.0)
check("puissance relevee resserre la fourchette",
      mesure["energie_kwh_fourchette"][0] == mesure["energie_kwh_fourchette"][1])
check("source de puissance annoncee", "relevee" in mesure["puissance_gpu_source"])
check("duree nulle -> energie nulle",
      hardware.estimer_energie(gpus=1, coeurs=1, secondes=0)["energie_kwh"] == 0)

print("\n-- lecture d'un rapport nsys --")
from romeo_mcp.noyau import _resumer_tableau  # noqa: E402

tableau = [
    " Time (%)  Total Time (ns)  Instances   Avg (ns)   Name",
    " --------  ---------------  ---------  ---------  ------",
    "     62,3      12,345,678       1,000    12,345.6  ampere_sgemm_128x64",
    "     21,7       4,300,000         500     8,600.0  elementwise_kernel",
    "      5,0       1,000,000         250     4,000.0  reduce_kernel",
]
lignes = _resumer_tableau(tableau, 2)
check("deux entrees retenues", len(lignes) == 2, len(lignes))
check("pourcentage a virgule lu", lignes[0]["part_pct"] == 62.3, lignes[0]["part_pct"])
check("separateurs de milliers absorbes", lignes[0]["temps_total_ns"] == 12345678)
check("nom du noyau conserve", "sgemm" in lignes[0]["nom"])
check("tableau sans donnees -> liste vide", _resumer_tableau(["du texte"], 3) == [])


print(chr(10) + "-- MPI : le cas generique du cluster --")
mpi = plan_job(
    JobSpec(name="mpi", command="./solveur.out", time="10m", nodes=4,
            cpus_per_task=1, distributed="mpi",
            spack_packages=["openmpi@4.1.7"]), SCRATCH)
check("prefixe srun, forme documentee", "srun ./solveur.out" in mpi.script)
check("aucun rendez-vous PyTorch impose", "MASTER_ADDR" not in mpi.script)
check("aucun NCCL impose", "NCCL" not in mpi.script)
check("MPI sans GPU accepte", mpi.total_gpus == 0)
check("architecture scalaire par defaut", mpi.arch == "x64cpu", mpi.arch)
check("topologie laissee a l'utilisateur", mpi.spec.ntasks_per_node == 1)
check("aucun cache Python impose", "HF_HOME" not in mpi.script)

mpi_gpu = plan_job(
    JobSpec(name="mpigpu", command="./solveur.out", time="10m", nodes=2,
            gpus_per_node=2, cpus_per_task=8, distributed="mpi"), SCRATCH)
check("MPI avec GPU accepte aussi", mpi_gpu.total_gpus == 4)

# Les familles PyTorch, elles, exigent bien des GPU.
try:
    plan_job(JobSpec(name="x", command="a", time="1h", distributed="ddp",
                     gpus_per_node=0), SCRATCH)
    check("ddp sans GPU refuse", False, "aucune erreur")
except ClusterError as exc:
    check("ddp sans GPU refuse", "mpi" in str(exc), str(exc))

print("\n-- decodage universel des codes de sortie --")
from romeo_mcp.diagnostics import decoder_code_sortie  # noqa: E402

# SLURM note `code:signal`. Un meme signal apparait donc sous deux formes
# selon que c'est le shell ou SLURM qui le rapporte.
for forme_a, forme_b, attendu in [
    ("0:9", "137:0", "SIGKILL"),
    ("0:11", "139:0", "SIGSEGV"),
    ("0:15", "143:0", "SIGTERM"),
]:
    a, b = decoder_code_sortie(forme_a), decoder_code_sortie(forme_b)
    check("{} reconnu sous les deux formes".format(attendu),
          a and b and a["nom"] == b["nom"] == attendu, (a, b))

for code, mot in [("127:0", "introuvable"), ("126:0", "executable"),
                  ("1:0", "generique")]:
    r = decoder_code_sortie(code)
    check("code {} explique".format(code), r and mot in r["libelle"], r)
check("127 renvoie a l'environnement absent",
      any("romeo_load_" in x for x in decoder_code_sortie("127:0")["remedes"]))
check("succes ne produit rien", decoder_code_sortie("0:0") is None)
check("champ vide tolere", decoder_code_sortie("") is None)
check("code inconnu decrit quand meme",
      "42" in (decoder_code_sortie("42:0") or {}).get("libelle", ""))

from romeo_mcp.diagnostics import analyser  # noqa: E402

r = analyser("FAILED", "137:0", "")
check("SIGKILL diagnostique sans journal",
      any(c["cle"] == "signal_9" for c in r["causes"]), cles(r))
check("code decode joint au rapport", r["code_decode"]["nom"] == "SIGKILL")
r = analyser("COMPLETED", "0:0", "tout va bien")
check("job sain : aucune cause", r["causes"] == [])

print("\n-- file de nettoyage unique --")
net = "\n".join(templates.preambule_nettoyage())
check("un seul piege EXIT", net.count("trap ") == 1, net.count("trap "))
check("file declaree", "_ROMEO_NETTOYAGE=()" in net)

tmp = "\n".join(templates.preambule_tmpdir("/scratch_p/moi", ["*.log"]))
check("TMPDIR propre au job", 'export TMPDIR="/scratch_p/moi/job_$SLURM_JOB_ID"' in tmp)
check("resultats rapatries avant destruction",
      tmp.index("cp -a") < tmp.index('rm -rf "$TMPDIR"'))
check("motif personnalise respecte", '"$TMPDIR"/*.log' in tmp)
check("nettoyage empile, pas de trap propre", "trap " not in tmp)

# Deux preambules qui nettoient ne doivent pas s'ecraser mutuellement.
combine = plan_job(
    JobSpec(name="deux", command="./calcul", time="30m",
            job_tmpdir=True, stage_archive="/scratch_p/moi/d.tar"), SCRATCH)
check("un seul trap malgre deux nettoyages",
      combine.script.count("trap _romeo_nettoyer EXIT") == 1
      and combine.script.count("trap ") == 1, combine.script.count("trap "))
check("les deux nettoyages sont enfiles",
      combine.script.count("_ROMEO_NETTOYAGE+=") == 2)

print("\n-- placement hybride MPI + OpenMP --")
check("liaison aux coeurs si plusieurs fils", templates.options_affinite(8) == "--cpu-bind=cores")
check("aucune liaison si un seul fil", templates.options_affinite(1) == "")
check("mode force respecte",
      templates.options_affinite(1, "threads") == "--cpu-bind=threads")

hyb = plan_job(
    JobSpec(name="hyb", command="./solveur", time="1h", nodes=2,
            ntasks_per_node=4, cpus_per_task=24, distributed="mpi",
            arch="x64cpu"), SCRATCH)
check("affinite injectee", "srun --cpu-bind=cores ./solveur" in hyb.script)
check("OMP_NUM_THREADS derive de SLURM",
      "export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-1}" in hyb.script)
check("96 coeurs par noeud declares", "--cpus-per-task=24" in hyb.script)

# Beaucoup de rangs sequentiels sur un noeud dense : gaspillage a signaler.
maigre = plan_job(
    JobSpec(name="maigre", command="srun ./a.out", time="1h", nodes=1,
            ntasks_per_node=4, cpus_per_task=1, arch="x64cpu"), SCRATCH)
check("sous-utilisation des coeurs signalee",
      any("OpenMP" in w for w in maigre.warnings), maigre.warnings)
plein = plan_job(
    JobSpec(name="plein", command="srun ./a.out", time="1h", nodes=1,
            ntasks_per_node=96, cpus_per_task=2, arch="x64cpu"), SCRATCH)
check("noeud bien rempli : pas d'avertissement",
      not any("OpenMP" in w for w in plein.warnings), plein.warnings)

print("\n-- secrets hors du script --")
sec = plan_job(
    JobSpec(name="sec", command="./a.out", time="30m",
            secret_env_file="/home/moi/.romeo-mcp/secrets.env"), SCRATCH)
check("fichier source, valeurs absentes",
      ". \"/home/moi/.romeo-mcp/secrets.env\"" in sec.script)
check("export automatique des variables lues", "set -a" in sec.script)
check("echec explicite si illisible", "exit 1" in sec.script)

raise SystemExit(bilan("TESTS DE CHARGES"))
