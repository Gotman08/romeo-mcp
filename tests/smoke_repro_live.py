"""Test volontaire sur ROMEO : un job CPU d'une minute au maximum.

Le registre et les rapports de test restent sous ~/.romeo-mcp/test-runs.
Les petits fichiers distants sont conserves pour permettre le diagnostic.
"""

import asyncio
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mcp import ClientSession, StdioServerParameters, stdio_client
from romeo_mcp.config import setting
from romeo_mcp.ssh import RomeoSession


async def main(resume=""):
    name = "mcp-repro-" + uuid.uuid4().hex[:10]
    local = Path(resume).expanduser() if resume else Path.home() / ".romeo-mcp" / "test-runs" / name
    saved = json.loads((local / "job.json").read_text(encoding="utf-8")) if resume else None
    if not saved:
        local.mkdir(parents=True, mode=0o700)
    ssh = RomeoSession(host=setting("ROMEO_HOST", "romeo1"))
    try:
        remote = saved["workdir"] if saved else ssh.scratch.rstrip("/") + "/mcp-tests/" + name
        fixture = "2\n3\n5\n7\n"
        if not saved:
            ssh.write_file(remote + "/input.txt", fixture, mode="600")
            ssh.write_file(remote + "/calculation.py",
                "from pathlib import Path\nvalues = [int(x) for x in Path('input.txt').read_text().split()]\n"
                "assert sum(x*x for x in values) == 87\nprint('REPRO_SCIENCE_OK')\n", mode="600")
            ssh.write_file(remote + "/.gitignore", ".romeo-provenance/\n*.sbatch\n*.out\n*.err\n", mode="600")
            ssh.run("git init -q\ngit add input.txt calculation.py .gitignore\n"
                    "git -c core.hooksPath=/dev/null -c commit.gpgsign=false -c user.name=ROMEO-test "
                    "-c user.email=romeo-test@example.org commit -qm 'Reproducibility smoke fixture'",
                    cwd=remote, timeout=30).check("fixture Git")
        commit = ssh.run("git rev-parse HEAD", cwd=remote).stdout.strip()
        assert len(commit) == 40, "Commit de la fixture introuvable"
        env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONIOENCODING": "utf-8",
               "ROMEO_MCP_DB": str(local / "jobs.db"), "ROMEO_TOOL_PROFILE": "essential"}
        params = StdioServerParameters(command=sys.executable, args=["-m", "romeo_mcp"], env=env)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()

                async def call(tool, arguments):
                    result = await client.call_tool(tool, arguments)
                    payload = json.loads(result.content[0].text)
                    # Les details restent dans le dossier prive en cas d'echec.
                    if result.is_error or not payload.get("ok"):
                        (local / "failure.json").write_text(json.dumps(payload), encoding="utf-8")
                        raise AssertionError(tool + " a echoue ; voir le dossier prive du test")
                    return payload

                profile = await call("tool_profile_get", {})
                assert profile["profile"] == "essential" and profile["count"] == 22
                spec = {"name": name, "command": "python3 calculation.py", "arch": "x64cpu",
                        "nodes": 1, "cpus_per_task": 1, "mem_gb": 1, "time_limit": "1m",
                        "workdir": remote, "data_files": [remote + "/input.txt"]}
                if saved:
                    jid = saved["job_id"]
                    print("Reprise du controle du job : " + jid, flush=True)
                else:
                    preview = await call("job_prepare", spec)
                    assert not preview["submitted"]
                    ssh.write_file(remote + "/preview.sbatch", preview["script"], mode="600")
                    ssh.run("bash -n " + shlex.quote(remote + "/preview.sbatch")).check("syntaxe Bash")
                    submitted = await call("job_submit", {"plan_id": preview["plan_id"], "confirm": True})
                    jid = submitted["job_id"]
                    (local / "job.json").write_text(json.dumps({"job_id": jid, "workdir": remote}), encoding="utf-8")
                    print("Job de controle soumis : " + jid, flush=True)
                deadline = time.monotonic() + 300
                previous = None
                while time.monotonic() < deadline:
                    status = await call("job_status", {"job_id": jid})
                    state = status.get("state")
                    if state != previous:
                        print("Etat : " + str(state), flush=True)
                        previous = state
                    if state == "COMPLETED":
                        break
                    if state in {"FAILED", "CANCELLED", "TIMEOUT", "OUT_OF_MEMORY", "NODE_FAIL"}:
                        raise AssertionError("Job de controle termine en echec : " + str(state))
                    await asyncio.sleep(5)
                else:
                    raise AssertionError("Attente depassee ; le job reste soumis, consulter son etat avant de relancer")
                output = await call("job_log_tail", {"job_id": jid, "stream": "out"})
                assert "REPRO_SCIENCE_OK" in json.dumps(output), "Resultat scientifique absent"
                snapshot = await call("job_report_collect", {"job_id": jid, "data_files": [remote + "/input.txt"]})
                result = await call("job_report_export", {"report_id": snapshot["report_id"], "output_dir": str(local)})
                report = json.loads(Path(result["files"]["report.json"]).read_text(encoding="utf-8"))
                assert report["submission"]["code"]["commit"] == commit
                assert report["runtime"]["git"]["commit"] == commit
                expected = hashlib.sha256(fixture.encode()).hexdigest()
                assert report["runtime"]["data"][0]["sha256"] == expected
                assert report["observations"]["data"][0]["sha256"] == expected
                assert report["runtime"]["environment"]["architecture"] == "x86_64"
                assert any(r["JobID"] == jid and r["State"] == "COMPLETED" and int(r["AllocCPUS"]) >= 1
                           for r in report["resource_usage"])
                assert not report["missing_information"], report["missing_information"]
                assert hashlib.sha256(report["script"]["content"].encode()).hexdigest() == report["script"]["exported_sha256"]
                snapshot = await call("job_report_from_record", {"job_id": jid})
                offline = await call("job_report_export", {"report_id": snapshot["report_id"], "output_dir": str(local)})
                assert offline["ok"] and offline["missing_information"]
                print("OK : protocole essentiel, calcul, commit, environnement, SHA-256, Slurm, exports live et hors ligne", flush=True)
    finally:
        ssh.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", default="", help="dossier local d'un test interrompu ; aucune nouvelle soumission")
    asyncio.run(main(parser.parse_args().resume))
