"""Verification en conditions reelles des charges de travail.

Soumet de vrais jobs volontairement defaillants et verifie que le diagnostic
les explique correctement.
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from commun import bilan, check  # noqa: E402
from romeo_mcp import server as srv  # noqa: E402


def lancer_et_attendre(nom, commande, time_limit="5m", attente=420):
    plan = srv.job_prepare(name=nom, command=commande, time_limit=time_limit, cpus_per_task=2)
    r = srv.job_submit(plan["plan_id"], confirm=True) if plan["ok"] else plan
    if not r.get("ok"):
        return None, r.get("error")
    jid = r["job_id"]
    srv.wait_for_job(jid, timeout_seconds=attente, poll_seconds=10)
    return jid, None


def main() -> int:
    print("== 1. Echec applicatif : module Python absent ==")
    jid, err = lancer_et_attendre(
        "mcp-ia-mod", 'python3 -c "import module_totalement_inexistant_xyz"')
    if err:
        check("soumission", False, err)
    else:
        time.sleep(6)
        d = srv.diagnose_job(jid)
        cles = [c["cle"] for c in d.get("causes", [])]
        print("   etat={} causes={}".format(d.get("etat"), cles))
        check("diagnostic rendu", d.get("ok") is True)
        check("module_python reconnu", "module_python" in cles, cles)
        if "module_python" in cles:
            cause = next(c for c in d["causes"] if c["cle"] == "module_python")
            print("   preuve  :", cause["preuve"].replace("\n", " ")[:110])
            print("   remede  :", cause["remedes"][0][:110])
            check("preuve extraite du journal", "module_totalement" in cause["preuve"])
        # `duree` a ete harmonise en `duration_seconds` : meme notion, un seul
        # nom dans tout le serveur.
        check("mesures jointes",
              "limites" in d and d["limites"].get("duration_seconds") is not None,
              d.get("limites"))

    print("\n== 2. Depassement de temps ==")
    jid2, err2 = lancer_et_attendre("mcp-ia-timeout", "sleep 300", time_limit="1m")
    if err2:
        check("soumission", False, err2)
    else:
        time.sleep(6)
        d = srv.diagnose_job(jid2)
        cles = [c["cle"] for c in d.get("causes", [])]
        print("   etat={} causes={}".format(d.get("etat"), cles))
        check("TIMEOUT reconnu", "temps" in cles, cles)
        check("recherche de reprise effectuee", "reprise" in d, list(d))
        if "reprise" in d:
            print("   reprise :", str(d["reprise"])[:120])

    print("\n== 3. Tableau de balayage parametrique ==")
    params = ["lr=0.1 seed=1", "lr=0.01 seed=2", "lr=0.001 seed=3", "lr=0.0001 seed=4"]
    dry = srv.job_array_prepare(name="mcp-ia-sweep", command='echo "run: $PARAMS"',
                               parameters=params, max_concurrent=2, time_limit="5m")
    check("simulation ne soumet rien", dry.get("submitted") is False)
    check("plage de tableau correcte",
          dry.get("resolved", {}).get("array") == "0-3%2",
          dry.get("resolved", {}).get("array"))
    check("PARAMS injecte dans le script", "$SLURM_ARRAY_TASK_ID" in dry.get("script", ""))

    reel = srv.job_array_submit(dry["plan_id"], confirm=True) if dry["ok"] else dry
    if not reel.get("ok"):
        check("soumission du tableau", False, reel.get("error"))
    else:
        aid = reel["job_id"]
        print("   tableau {} ({} taches)".format(aid, len(params)))
        srv.wait_for_job(aid, timeout_seconds=420, poll_seconds=10)
        time.sleep(5)
        sortie = srv.job_log_tail(aid, stream="out", lines=60)
        contenu = sortie.get("content", "")
        trouves = sum(1 for p in params if "run: {}".format(p) in contenu)
        print("   jeux retrouves dans les sorties : {}/{}".format(trouves, len(params)))
        check("chaque tache a recu ses parametres", trouves == len(params), contenu[:200])

    print("\n== 4. Service interactif (simulation) ==")
    svc = srv.service_prepare(config={"service": "jupyter", "env_path": "/scratch_p/user/venv", "port": 2345},
                                         time_limit="1h", gpus_per_node=1)
    check("simulation par defaut", svc.get("submitted") is False)
    check("commande de service generee", "jupyter lab" in svc.get("script", ""))
    check("port repercute", "2345" in svc.get("script", ""))
    mauvais = srv.service_prepare(config={"service": "tensorboard", "env_path": "/scratch_p/user/venv"})
    check("tensorboard exige un logdir", not mauvais.get("ok"))
    inconnu = srv.service_prepare(config={"service": "grafana", "env_path": "/scratch_p/user/venv"})
    check("service inconnu refuse", not inconnu.get("ok"))

    print("\n== 5. Noeud de mise au point (simulation) ==")
    dbg = srv.cluster_allocation_prepare(time_limit="15m", arch="armgpu", gpus_per_node=1)
    check("simulation par defaut", dbg.get("submitted") is False)
    check("arch armgpu retenue", dbg.get("resolved", {}).get("arch") == "armgpu")

    print("\n== 6. Inventaire du stockage ==")
    st = srv.storage_usage_audit(top=5)
    check("inventaire rendu", st.get("ok") is True, st.get("error"))
    if st.get("ok"):
        print("   repertoires : {}".format(
            [d["taille"] + " " + d["path"].split("/")[-1] for d in st["repertoires"][:4]]))
        check("suggestions fournies", len(st.get("suggestions", [])) >= 1)
        check("ne supprime rien",
              any("ne supprime rien" in s for s in st.get("suggestions", [])))

    print("\n== 7. Ressources dynamiques ==")
    charge = srv.cluster_load()
    check("charge du cluster lisible", "armgpu" in charge, charge[:80])
    jobs = srv.jobs_running()
    check("jobs en cours lisible", "Jobs en cours" in jobs)

    print("\n== 8. Telemetrie en direct et trace de pile ==")
    plan_temoin = srv.job_prepare(
        name="mcp-live", time_limit="10m", gpus_per_node=1, cpus_per_task=8,
        command='python3 -c "import time; [time.sleep(1) for _ in range(500)]"',
    )
    temoin = srv.job_submit(plan_temoin["plan_id"], confirm=True) if plan_temoin["ok"] else plan_temoin
    if not temoin.get("ok"):
        check("job temoin", False, temoin.get("error"))
    else:
        tid = temoin["job_id"]
        # La sonde ne s'applique qu'a un job RUNNING : on attend son demarrage.
        for _ in range(40):
            if srv.job_status(tid).get("state") == "RUNNING":
                break
            time.sleep(8)

        mesures = srv.job_live_metrics(tid)
        if not mesures.get("ok"):
            check("telemetrie", False, mesures.get("error"))
        else:
            gpus = mesures.get("gpus", [])
            print("   GPU sondes : {} | constats : {}".format(
                len(gpus), len(mesures.get("constats", []))))
            check("au moins un GPU sonde", len(gpus) >= 1)
            if gpus:
                check("VRAM coherente avec un GH200",
                      90000 < (gpus[0]["vram_totale_mib"] or 0) < 110000,
                      gpus[0]["vram_totale_mib"])
                check("temperature relevee", (gpus[0]["temperature_c"] or 0) > 0)
            # Le temoin ne fait que dormir : l'inactivite doit etre signalee.
            check("inactivite GPU signalee",
                  any("attend" in c for c in mesures.get("constats", [])),
                  mesures.get("constats"))
            check("processus listes", len(mesures.get("processus", [])) >= 1)

        pile = srv.job_stack_trace(tid, process_name="python3")
        if not pile.get("ok"):
            check("trace de pile", False, pile.get("error"))
        else:
            plat = " ".join(l for tr in pile["traces"] for l in tr["pile"])
            check("pile capturee", pile["processus_traces"] >= 1)
            check("pile d'un processus endormi", "sleep" in plat.lower(), plat[:120])
            check("aucun faux positif CUDA",
                  not any("CUDA" in i for i in pile.get("indices", [])),
                  pile.get("indices"))

        srv.cancel_job(tid)
        time.sleep(10)
        refus = srv.job_live_metrics(tid)
        check("sonde refusee sur job arrete", not refus.get("ok"))

    print("\n== 9. Ordonnancement ==")
    slot = srv.suggest_submission_slot(nodes=1, gpus_per_node=1, hours=0.5)
    check("30 min renvoie vers instant", slot.get("recommandation") == "instant",
          slot.get("recommandation"))
    slot3 = srv.suggest_submission_slot(nodes=1, gpus_per_node=1, hours=3)
    check("3 h renvoie vers short", slot3.get("recommandation") == "short",
          slot3.get("recommandation"))
    fc = srv.romeo_fairshare_forecast(simulated_cpus=64, simulated_gpus=1,
                                      duration_hours=2)
    check("prevision d'usage rendue", fc.get("ok") is True, fc.get("error"))
    if fc.get("ok"):
        print("   usage actuel {} -> hausse {} %".format(
            fc.get("usage_brut_actuel"), fc.get("hausse_relative_pct")))
        check("cout calcule",
              fc["charge_simulee"]["cout_coeur_secondes"] == 64 * 2 * 3600)
        check("limites du modele explicitees",
              any("pas publique" in l for l in fc.get("lecture", [])))

    return bilan("CHARGES DE TRAVAIL")


if __name__ == "__main__":
    raise SystemExit(main())
