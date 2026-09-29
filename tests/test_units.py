"""Tests unitaires sans acces reseau : validation, generation sbatch, garde-fous."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from commun import bilan, check  # noqa: E402,F401
from commun import expect_error as _expect_error  # noqa: E402
import offline  # valeurs fictives, aucun acces reseau
from romeo_mcp import cluster, guard, slurm  # noqa: E402


def expect_error(label, fn, needle=""):
    """Restreint le harnais aux erreurs du domaine.

    Attraper n'importe quelle exception masquerait une erreur de programmation
    dans le test lui-meme et la ferait passer pour un refus attendu.
    """
    return _expect_error(
        label, fn, needle, exceptions=(cluster.ClusterError, guard.GuardError)
    )


print("\n-- durees --")
check("2h", cluster.parse_duration("2h") == 7200)
check("30m", cluster.parse_duration("30m") == 1800)
check("1d", cluster.parse_duration("1d") == 86400)
check("1:30:00", cluster.parse_duration("1:30:00") == 5400)
check("30:00 (MM:SS)", cluster.parse_duration("30:00") == 1800)
check("2-00:00:00", cluster.parse_duration("2-00:00:00") == 172800)
check("entier = minutes", cluster.parse_duration("90") == 5400)
check("format 5400", cluster.format_slurm_time(5400) == "01:30:00")
check("format 172800", cluster.format_slurm_time(172800) == "2-00:00:00")
expect_error("duree illisible refusee", lambda: cluster.parse_duration("bientot"))

print("\n-- partitions --")
check("30 min -> instant", cluster.pick_partition(1800) == "instant")
check("2 h -> short", cluster.pick_partition(7200) == "short")
check("3 j -> long", cluster.pick_partition(3 * 86400) == "long")
expect_error("> 30 j refuse", lambda: cluster.pick_partition(40 * 86400), "30 jours")

print("\n-- architecture --")
check("gpu implique armgpu", cluster.resolve_arch(None, 4) == "armgpu")
check("cpu par defaut", cluster.resolve_arch(None, 0) == "x64cpu")
check("alias gpu", cluster.resolve_arch("gpu", 1) == "armgpu")
check("alias x86", cluster.resolve_arch("x86_64", 0) == "x64cpu")
expect_error(
    "x64cpu + gpu refuse", lambda: cluster.resolve_arch("x64cpu", 2), "incompatible"
)
expect_error("arch inconnue refusee", lambda: cluster.resolve_arch("sparc", 0))

print("\n-- plan de job --")
plan = slurm.plan_job(
    slurm.JobSpec(name="essai", command="python train.py", time="2h",
                  gpus_per_node=4, cpus_per_task=32, mem_gb=400),
    "/scratch_p/moi",
)
check("partition deduite = short", plan.partition == "short", plan.partition)
check("arch deduite = armgpu", plan.arch == "armgpu")
check("contrainte armgpu dans le script", "--constraint=armgpu" in plan.script)
check("gpus-per-node (forme documentee)", "--gpus-per-node=4" in plan.script)
check("plus de --gres", "--gres" not in plan.script)
check("compte injecte", "--account=test-project" in plan.script)
check("time correct", "--time=02:00:00" in plan.script)
check("mem correcte", "--mem=400G" in plan.script)
check("shebang documente", plan.script.startswith("#!/usr/bin/env bash"))
check("env loader inconditionnel", "romeo_load_armgpu_env" in plan.script)
check("pas de module purge sans modules", "module purge" not in plan.script)
check("workdir sous scratch", plan.workdir.startswith("/scratch_p/moi"))
check("avertissement aarch64", any("aarch64" in w for w in plan.warnings))
check("total cpus", plan.total_cpus == 32, plan.total_cpus)
check("total gpus", plan.total_gpus == 4)

plan2 = slurm.plan_job(
    slurm.JobSpec(name="tab", command="echo $SLURM_ARRAY_TASK_ID", time="20m",
                  array="0-9%3"),
    "/scratch_p/moi",
)
check("tableau accepte", "--array=0-9%3" in plan2.script)
check("motif de log en tableau", "%x-%A_%a.out" in plan2.script)
check("partition instant", plan2.partition == "instant")
check("contrainte x64cpu", "--constraint=x64cpu" in plan2.script)

print("\n-- refus de dimensionnement --")
expect_error(
    "temps > partition forcee",
    lambda: slurm.plan_job(
        slurm.JobSpec(name="x", command="a", time="5h", partition="instant"),
        "/scratch_p/moi"),
    "depasse la limite",
)
expect_error(
    "trop de coeurs par noeud",
    lambda: slurm.plan_job(
        slurm.JobSpec(name="x", command="a", cpus_per_task=999), "/scratch_p/moi"),
    "coeurs par noeud",
)
expect_error(
    "trop de GPU",
    lambda: slurm.plan_job(
        slurm.JobSpec(name="x", command="a", gpus_per_node=8), "/scratch_p/moi"),
    "GPU par noeud",
)
expect_error(
    "trop de noeuds",
    lambda: slurm.plan_job(
        slurm.JobSpec(name="x", command="a", nodes=200), "/scratch_p/moi"),
    "noeuds demandes",
)
expect_error(
    "memoire hors capacite",
    lambda: slurm.plan_job(
        slurm.JobSpec(name="x", command="a", gpus_per_node=1, mem_gb=5000),
        "/scratch_p/moi"),
    "Go par noeud demandes",
)
expect_error(
    "nom invalide",
    lambda: slurm.plan_job(
        slurm.JobSpec(name="mon job !", command="a"), "/scratch_p/moi"),
    "nom de job invalide",
)
expect_error(
    "commande vide",
    lambda: slurm.plan_job(slurm.JobSpec(name="x", command="  "), "/scratch_p/moi"),
    "commande vide",
)
expect_error(
    "tableau invalide",
    lambda: slurm.plan_job(
        slurm.JobSpec(name="x", command="a", array="tout"), "/scratch_p/moi"),
    "tableau invalide",
)

print("\n-- lecture sacct --")
check("MM:SS.mmm", abs(slurm.parse_sacct_duration("02:30.500") - 150.5) < 0.01)
check("HH:MM:SS", slurm.parse_sacct_duration("01:00:00") == 3600)
check("D-HH:MM:SS", slurm.parse_sacct_duration("1-02:00:00") == 93600)
check("memoire K", abs(slurm.parse_mem_mb("2048K") - 2.0) < 0.01)
check("memoire G", abs(slurm.parse_mem_mb("4G") - 4096.0) < 0.01)
check("gpu depuis TRES", slurm.gpus_from_tres("cpu=32,gres/gpu:h100=4,mem=400G") == 4)
check("pas de gpu", slurm.gpus_from_tres("cpu=8,mem=16G") == 0)

rows = slurm.parse_pipe_table(
    "JobID|JobName|Partition|State|ExitCode|Elapsed|TotalCPU|AllocCPUS|ReqMem|MaxRSS|AllocTRES\n"
    "999|essai|short|COMPLETED|0:0|01:00:00|08:00:00|32|400G||cpu=32,gres/gpu:h100=4\n"
    "999.batch|batch||COMPLETED|0:0|01:00:00|08:00:00|32||120G|cpu=32\n"
)
eff = slurm.summarize_efficiency(rows, "999")
check("efficacite trouvee", eff["found"])
# 8 h de CPU sur 1 h x 32 coeurs = 32 h reservees -> 25 %
check("efficacite CPU 25 %", eff["cpu_efficiency_pct"] == 25.0, eff["cpu_efficiency_pct"])
check("memoire 120G/400G = 30 %", eff["mem_efficiency_pct"] == 30.0, eff["mem_efficiency_pct"])
check("gpu detectes", eff["alloc_gpus"] == 4)
check("conseil de reduction memoire", any("baisse mem_gb" in a for a in eff["advice"]),
      eff["advice"])
check("job absent", not slurm.summarize_efficiency(rows, "123")["found"])

print("\n-- garde-fous du noeud de login --")
for bad, needle in [
    ("make -j 32", "compute_command_prepare"),
    ("cd src && make", "compute_command_prepare"),
    ("gcc -O3 main.c", "compute_command_prepare"),
    ("nvcc kernel.cu", "compute_command_prepare"),
    ("mpirun -n 4 ./a.out", "job_prepare"),
    ("pip install torch", "aarch64"),
    ("python3 -m pip install numpy", "aarch64"),
    ("python train.py", "job_prepare"),
    ("ls && python entrainement.py --epochs 10", "job_prepare"),
    ("rm -rf /", "irreversibles"),
    ("dd if=/dev/zero of=/dev/sda", "irreversibles"),
]:
    expect_error("refuse: {}".format(bad), lambda b=bad: guard.check_login_command(b), needle)

for good in [
    "ls -la",
    "git status",
    "grep -r TODO src",
    "python -c 'print(1)'",
    "python --version",
    "squeue -u $USER",
    "cat resultats.txt | head -20",
    "OMP_NUM_THREADS=4 echo test",
]:
    try:
        guard.check_login_command(good)
        check("autorise: {}".format(good), True)
    except guard.GuardError as exc:
        check("autorise: {}".format(good), False, str(exc))

print("\n-- perimetre des chemins --")
HOME, SCRATCH = "/home/moi", "/scratch_p/moi"
check("home ok", guard.check_path("~/code", HOME, SCRATCH) == "/home/moi/code")
check("relatif -> scratch",
      guard.check_path("run1/out", HOME, SCRATCH) == "/scratch_p/moi/run1/out")
check("absolu scratch ok",
      guard.check_path("/scratch_p/moi/x", HOME, SCRATCH) == "/scratch_p/moi/x")
check("normalisation", guard.check_path("/home/moi/a/../b", HOME, SCRATCH) == "/home/moi/b")
expect_error("hors perimetre", lambda: guard.check_path("/etc/passwd", HOME, SCRATCH),
             "hors perimetre")
expect_error("remontee refusee",
             lambda: guard.check_path("/home/moi/../../etc", HOME, SCRATCH),
             "hors perimetre")
expect_error("scratch d'autrui refuse",
             lambda: guard.check_path("/scratch_p/autre/x", HOME, SCRATCH),
             "hors perimetre")

print("\n-- noeuds disponibles par partition --")
expect_error(
    "50 noeuds armgpu sur long (40 dispo)",
    lambda: slurm.plan_job(
        slurm.JobSpec(name="x", command="a", nodes=50, arch="armgpu", time="5d"),
        "/scratch_p/moi"),
    "n'en expose que 40",
)
expect_error(
    "30 noeuds x64cpu sur long (24 dispo)",
    lambda: slurm.plan_job(
        slurm.JobSpec(name="x", command="a", nodes=30, arch="x64cpu", time="5d"),
        "/scratch_p/moi"),
    "n'en expose que 24",
)
ok50 = slurm.plan_job(
    slurm.JobSpec(name="x", command="srun a", nodes=50, arch="armgpu", time="30m"),
    "/scratch_p/moi")
check("50 noeuds armgpu sur instant (58 dispo) accepte", ok50.partition == "instant")

print("\n-- plafonds du compte --")
gros = slurm.plan_job(
    slurm.JobSpec(name="x", command="srun a", nodes=8, cpus_per_task=288,
                  arch="armgpu", time="30m"),
    "/scratch_p/moi")
check("avertissement 2304 coeurs > 1024",
      any("1024" in w for w in gros.warnings), gros.warnings)
gpus = slurm.plan_job(
    slurm.JobSpec(name="x", command="srun a", nodes=20, gpus_per_node=4, time="30m"),
    "/scratch_p/moi")
check("avertissement 80 GPU > 16",
      any("plafonne a 16" in w for w in gpus.warnings), gpus.warnings)

print("\n-- avertissement MPI --")
sans = slurm.plan_job(
    slurm.JobSpec(name="x", command="./mon_calcul", nodes=2, ntasks_per_node=4,
                  time="30m"), "/scratch_p/moi")
check("multi-taches sans srun -> avertissement",
      any("ni srun ni mpirun" in w for w in sans.warnings), sans.warnings)
avec = slurm.plan_job(
    slurm.JobSpec(name="x", command="srun ./mon_calcul", nodes=2, ntasks_per_node=4,
                  time="30m"), "/scratch_p/moi")
check("avec srun -> pas d'avertissement MPI",
      not any("ni srun ni mpirun" in w for w in avec.warnings))
mono = slurm.plan_job(
    slurm.JobSpec(name="x", command="./calcul", time="30m"), "/scratch_p/moi")
check("mono-tache -> pas d'avertissement MPI",
      not any("ni srun ni mpirun" in w for w in mono.warnings))

print("\n-- garde-fous revises --")
try:
    guard.check_login_command("srun --pty bash")
    check("srun autorise (voie officielle vers un noeud)", True)
except guard.GuardError as exc:
    check("srun autorise (voie officielle vers un noeud)", False, str(exc))
try:
    guard.check_login_command("pip install numpy", allow_heavy=True)
    check("allow_heavy leve le refus de pip", True)
except guard.GuardError as exc:
    check("allow_heavy leve le refus de pip", False, str(exc))
expect_error(
    "allow_heavy ne leve PAS le refus destructeur",
    lambda: guard.check_login_command("rm -rf /", allow_heavy=True),
    "irreversibles",
)

print("\n-- espaces autorises --")
check("espace projet officiel",
      guard.check_path("/project/test-project/data", HOME, SCRATCH) == "/project/test-project/data")
check("gpfs/projet accepte aussi",
      guard.check_path("/gpfs/projet/x", HOME, SCRATCH) == "/gpfs/projet/x")
check("apps lisible",
      guard.check_path("/apps/2025/manual_install", HOME, SCRATCH).startswith("/apps"))
expect_error("etc toujours refuse",
             lambda: guard.check_path("/etc/passwd", HOME, SCRATCH), "hors perimetre")

raise SystemExit(bilan("TESTS UNITAIRES"))
