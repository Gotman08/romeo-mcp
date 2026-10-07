"""Verifie le serveur au niveau du protocole MCP : poignee de main stdio reelle."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp import ClientSession, StdioServerParameters, stdio_client  # noqa: E402

#: Inventaire fige de la surface publique du serveur. Toute divergence (outil
#: disparu ou ajoute sans mise a jour de cette liste) fait echouer la suite.
#: C'est le seul garde-fou contre une perte silencieuse lors d'un deplacement
#: de code entre modules.
OUTILS_ATTENDUS = {
    'checkpoint_export_prepare',
    'checkpoint_export_status',
    'checkpoint_inspect',
    'checkpoint_protect_prepare',
    'checkpoint_protect_submit',
    'job_checkpoint_request',
    'job_environment_status',
    'job_observation_get',
    'job_resume_prepare',
    'job_resume_submit',
    'job_resume_status',
    'mcp_diagnostics',
    'mcp_update_check',
    'mcp_update_policy',
    'mcp_update_rollback',
    'mcp_update_start',
    'mcp_update_status',
    'romeo_capabilities',
    'transfer_cancel',
    'transfer_prepare',
    'transfer_start',
    'transfer_status',
    'audit_orphan_files',
    'cancel_job',
    'cluster_allocation_connection_info',
    'cluster_allocation_prepare',
    'cluster_allocation_start',
    'cluster_gpu_health_run',
    'compute_command_prepare',
    'compute_command_run',
    'dataset_download',
    'dataset_prepare',
    'diagnose_job',
    'download_from_romeo',
    'file_create',
    'file_replace',
    'inject_io_staging',
    'job_array_prepare',
    'job_array_submit',
    'job_efficiency',
    'job_energy_footprint',
    'job_live_metrics',
    'job_log_search',
    'job_log_tail',
    'job_pipeline_prepare',
    'job_pipeline_submit',
    'job_prepare',
    'job_profile_prepare',
    'job_profile_submit',
    'job_report_collect',
    'job_report_export',
    'job_report_from_record',
    'job_report_get',
    'job_resilient_prepare',
    'job_resilient_submit',
    'job_stack_trace',
    'job_status',
    'job_submit',
    'job_system_health',
    'list_dir',
    'list_jobs',
    'login_command_run',
    'plan_get',
    'profile_report',
    'python_env_create',
    'python_env_prepare',
    'python_packages_install',
    'python_packages_prepare',
    'python_wheel_build',
    'python_wheel_prepare',
    'read_doc',
    'read_remote_file',
    'romeo_fairshare_forecast',
    'romeo_modules',
    'romeo_quota',
    'romeo_selfcheck',
    'romeo_software',
    'romeo_status',
    'sbatch_check_paths',
    'sbatch_validate',
    'search_docs',
    'secret_env_prepare',
    'service_connection_info',
    'service_prepare',
    'service_start',
    'service_status',
    'service_stop',
    'storage_usage_audit',
    'suggest_submission_slot',
    'tool_profile_get',
    'tool_profile_set',
    'upload_to_romeo',
    'wait_for_job',
}


def payload_of(result):
    """Les outils rendent du JSON dans content[0].text.

    mcp 2.0 ne remplit structured_content que si l'outil declare un schema
    de sortie ; un retour `dict` generique n'en produit pas.
    """
    return json.loads(result.content[0].text)


async def main() -> int:
    params = StdioServerParameters(command=sys.executable, args=["-m", "romeo_mcp", "serve", "--profile", "expert"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as sess:
            init = await sess.initialize()
            print("serveur :", init.server_info.name, init.server_info.version)

            tools = (await sess.list_tools()).tools
            print("\noutils exposes ({}) :".format(len(tools)))
            for tool in tools:
                read_only = (tool.annotations.read_only_hint
                             if tool.annotations else None)
                marque = "lecture " if read_only else "ecriture"
                print("  [{}] {:<22} {}".format(
                    marque, tool.name, (tool.description or "").split(".")[0][:70]))

            # L'inventaire est fige volontairement. Sans cette assertion, un
            # outil qui cesse d'etre enregistre (au fil d'un deplacement de
            # code, par exemple) disparaitrait sans que rien ne le signale.
            exposes = {t.name for t in tools}
            manquants = sorted(OUTILS_ATTENDUS - exposes)
            nouveaux = sorted(exposes - OUTILS_ATTENDUS)
            if manquants:
                print("\nOUTILS DISPARUS : {}".format(manquants))
            if nouveaux:
                print("\nOUTILS NON DECLARES dans smoke_protocol.py : {}".format(nouveaux))
                print("  -> ajoute-les a OUTILS_ATTENDUS si l'ajout est voulu.")
            assert not manquants, "outils disparus : {}".format(manquants)
            assert not nouveaux, "outils non declares : {}".format(nouveaux)

            # Un outil sans description ni annotation est inexploitable par un
            # modele : il ne sait ni a quoi il sert, ni s'il modifie l'etat.
            sans_description = sorted(
                t.name for t in tools if not (t.description or "").strip())
            sans_annotation = sorted(t.name for t in tools if t.annotations is None)
            assert not sans_description, "sans description : {}".format(sans_description)
            assert not sans_annotation, "sans annotation : {}".format(sans_annotation)
            print("\ninventaire conforme : {} outils, tous decrits et annotes".format(
                len(tools)))

            resources = (await sess.list_resources()).resources
            print("\nressources ({}) :".format(len(resources)))
            for res in resources:
                print("  {:<24} {}".format(str(res.uri), res.name))

            templates = (await sess.list_resource_templates()).resource_templates
            for tpl in templates:
                print("  {:<24} {} (modele)".format(str(tpl.uri_template), tpl.name))

            prompts = (await sess.list_prompts()).prompts
            print(chr(10) + "prompts ({}) :".format(len(prompts)))
            for pr in prompts:
                args = [a.name for a in (pr.arguments or [])]
                print("  {:<22} {} {}".format(pr.name, args,
                                              (pr.description or "")[:44]))
            assert {"optimize_for_gh200", "debug_slurm_failure",
                    "scale_to_multi_node"} <= {pr.name for pr in prompts}

            rendu = await sess.get_prompt("debug_slurm_failure",
                                          {"job_id": "123456"})
            corps = rendu.messages[0].content.text
            print(chr(10) + "prompt debug_slurm_failure : {} caracteres".format(len(corps)))
            assert "123456" in corps and "diagnose_job" in corps

            # Lecture de l'aide-memoire : c'est ce que le modele verra.
            content = await sess.read_resource("romeo://cheatsheet")
            text = content.contents[0].text
            print("\naide-memoire : {} caracteres".format(len(text)))
            assert "armgpu" in text and "--mem" in text

            # Appel d'outil reel a travers le protocole.
            result = await sess.call_tool("romeo_status", {"include_queue": False})
            data = payload_of(result)
            print("\nromeo_status via protocole : ok={} user={} noeuds armgpu libres={}".format(
                data.get("ok"), data.get("user"),
                (data.get("nodes") or {}).get("armgpu", {}).get("idle")))
            assert data.get("ok") is True

            # Simulation de soumission : doit rendre un script sans rien soumettre.
            dry = await sess.call_tool("job_prepare", {
                "name": "protocole", "command": "echo test",
                "time_limit": "10m", "gpus_per_node": 2, "cpus_per_task": 32,
            })
            payload = payload_of(dry)
            print("simulation : submitted={} partition={} arch={} mem auto={}".format(
                payload.get("submitted"),
                payload.get("resolved", {}).get("partition"),
                payload.get("resolved", {}).get("arch"),
                "--mem=" in payload.get("script", "")))
            assert payload.get("submitted") is False
            assert "--constraint=armgpu" in payload.get("script", "")
            assert "--gpus-per-node=2" in payload.get("script", "")

            # Refus : le garde-fou doit remonter proprement, pas planter.
            refused = await sess.call_tool("login_command_run", {"command": "make -j 8"})
            payload = payload_of(refused)
            print("refus via protocole : ok={} refused={}".format(
                payload.get("ok"), payload.get("refused")))
            assert payload.get("refused") is True

    print("\nPROTOCOLE MCP : TOUT PASSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
