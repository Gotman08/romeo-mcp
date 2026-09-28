"""Test de bout en bout contre ROMEO : soumet un job minuscule et le suit."""

import json
import sys
from pathlib import Path
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from romeo_mcp import server as srv  # noqa: E402


def show(label, payload, keys=None):
    print("\n== {} ==".format(label))
    if isinstance(payload, dict):
        if not payload.get("ok", True):
            print("  ERREUR:", payload.get("error"))
            return payload
        data = {k: payload[k] for k in keys if k in payload} if keys else payload
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str)[:1400])
    else:
        print(payload)
    return payload


def main() -> int:
    failures = []

    st = show("romeo_status", srv.romeo_status(), ["host", "user", "account", "nodes"])
    if not st.get("ok"):
        failures.append("romeo_status")

    mods = srv.romeo_modules(search="openmpi")
    print("\n== romeo_modules(openmpi) ==\n ", mods.get("modules"))
    if not mods.get("ok") or mods.get("count", 0) == 0:
        failures.append("romeo_modules")

    show("romeo_quota", srv.romeo_quota(), ["filesystems", "home", "scratch"])

    # --- simulation : rien ne doit partir --------------------------------
    dry = srv.job_prepare(
        name="mcp-verif",
        command='echo "bonjour depuis $(hostname)"; sleep 5',
        time_limit="5m",
    )
    print("\n== job_prepare (simulation) ==")
    print("  submitted:", dry.get("submitted"), "| partition:",
          dry.get("resolved", {}).get("partition"), "| arch:",
          dry.get("resolved", {}).get("arch"))
    print("  avertissements:", dry.get("warnings"))
    print("  --- script genere ---")
    print("\n".join("  " + l for l in dry.get("script", "").splitlines()))
    if dry.get("submitted") is not False:
        failures.append("simulation aurait soumis")

    # --- refus attendus ---------------------------------------------------
    print("\n== refus attendus ==")
    for bad in ["make -j 8", "pip install numpy", "python entrainement.py"]:
        r = srv.run_login_command(bad)
        ok = r.get("refused") is True
        print("  {:<28} refuse={} -> {}".format(bad, ok, str(r.get("error"))[:80]))
        if not ok:
            failures.append("refus manquant: " + bad)

    gpu_on_cpu = srv.job_prepare(name="x", command="a", arch="x64cpu", gpus_per_node=2)
    print("  gpu sur x64cpu refuse :", not gpu_on_cpu.get("ok"),
          "->", str(gpu_on_cpu.get("error"))[:90])
    if gpu_on_cpu.get("ok"):
        failures.append("incoherence arch/gpu non detectee")

    too_long = srv.job_prepare(name="x", command="a", time_limit="5h",
                              partition="instant")
    print("  temps > partition refuse :", not too_long.get("ok"),
          "->", str(too_long.get("error"))[:90])

    # --- commande legere autorisee ---------------------------------------
    ok_cmd = srv.run_login_command("hostname; uname -m")
    print("\n== run_login_command (autorise) ==\n ", ok_cmd.get("output"))
    if not ok_cmd.get("ok"):
        failures.append("run_login_command")

    # --- soumission reelle d'un job minuscule -----------------------------
    prepared = srv.job_prepare(
        name="mcp-verif",
        command='echo "bonjour depuis $(hostname) en $(uname -m)"; sleep 5; echo fini',
        time_limit="5m",
    )
    live = srv.job_submit(prepared["plan_id"], confirm=True) if prepared["ok"] else prepared
    show("job_submit (reel)", live, ["job_id", "resolved", "script_path", "stdout"])
    if not live.get("ok"):
        return _finish(failures + ["job_prepare reel"])
    job_id = live["job_id"]

    waited = srv.wait_for_job(job_id, timeout_seconds=180, poll_seconds=8)
    print("\n== wait_for_job ==\n  etat:", waited.get("state"),
          "| termine:", waited.get("finished"))

    out = srv.job_log_tail(job_id, stream="out", lines=20)
    print("\n== job_log_tail ==\n", out.get("content"))
    if "bonjour depuis" not in str(out.get("content", "")):
        failures.append("sortie du job absente")

    time.sleep(5)  # laisse la comptabilite SLURM se mettre a jour
    eff = srv.job_efficiency(job_id)
    show("job_efficiency", eff,
         ["state", "elapsed", "alloc_cpus", "cpu_efficiency_pct",
          "max_rss_mb", "mem_efficiency_pct", "advice"])
    if not eff.get("ok"):
        failures.append("job_efficiency")

    jobs = srv.list_jobs(limit=3)
    print("\n== list_jobs ==\n  en file:", len(jobs.get("in_queue", [])),
          "| connus du registre:", len(jobs.get("submitted_via_mcp", [])))
    if not jobs.get("submitted_via_mcp"):
        failures.append("registre vide")

    listing = srv.list_dir(live["resolved"]["workdir"])
    print("\n== list_dir(workdir) ==")
    for entry in listing.get("entries", [])[:6]:
        print("  {:<40} {}".format(entry["name"], entry["size"]))

    # --- la preuve par l'architecture -------------------------------------
    print("\n== build_on_node(armgpu) : le test decisif ==")
    build = srv.build_on_node(
        commands=['echo "architecture du noeud de calcul : $(uname -m)"'],
        arch="armgpu",
        minutes=2,
        cpus=4,
    )
    if build.get("ok"):
        print(build.get("output"))
        if "aarch64" not in str(build.get("output", "")):
            failures.append("le noeud armgpu n'a pas repondu aarch64")
    else:
        print("  ERREUR:", build.get("error"))
        failures.append("build_on_node")

    return _finish(failures)


def _finish(failures):
    print("\n" + "=" * 60)
    if failures:
        print("ECHECS ({}) : {}".format(len(failures), failures))
        return 1
    print("BOUT EN BOUT : TOUT PASSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
