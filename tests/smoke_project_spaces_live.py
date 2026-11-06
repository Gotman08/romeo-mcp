"""Test reel sur ROMEO : vrai serveur MCP, SSH, GPFS et un job Slurm d'une minute.

Cree le dossier personnel du login dans le projet choisi : c'est le comportement
attendu du serveur, ce dossier reste en place. Seuls les elements `mcp-essai-*`
de ce test sont retires a la fin. Rien n'est ecrit ailleurs dans le projet.

Usage :
    python tests/smoke_project_spaces_live.py --project CODE [--foreign-project CODE]

`--foreign-project` designe un projet ou le dossier du login appartient a un
autre compte : le serveur doit alors tout refuser sans rien modifier.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import posixpath
import shlex
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mcp import ClientSession, StdioServerParameters, stdio_client  # noqa: E402
from romeo_mcp.config import setting  # noqa: E402
from romeo_mcp.ssh import RomeoSession  # noqa: E402


class Essai:
    def __init__(self, client, witness, project, foreign):
        self.client, self.witness = client, witness
        self.login = witness.user
        self.root = "/project/" + project
        self.personal = "{}/{}".format(self.root, self.login)
        self.project = project
        self.foreign = foreign
        self.course = ""
        self.tag = "mcp-essai-" + uuid.uuid4().hex[:10]
        self.count = 0

    def ok(self, label):
        self.count += 1
        print("  OK  " + label, flush=True)

    async def call(self, tool, **arguments):
        result = await self.client.call_tool(tool, arguments)
        return json.loads(result.content[0].text)

    async def allowed(self, tool, **arguments):
        payload = await self.call(tool, **arguments)
        assert payload.get("ok") is True, "{} refuse : {}".format(tool, json.dumps(payload)[:800])
        return payload

    async def refused(self, tool, needle, **arguments):
        payload = await self.call(tool, **arguments)
        assert payload.get("ok") is False, "{} accepte a tort : {}".format(tool, json.dumps(payload)[:800])
        assert needle in payload.get("error", ""), "{} : refus inattendu : {}".format(tool, payload.get("error"))
        return payload

    def sh(self, command):
        """Temoin hors MCP : ce que le systeme de fichiers contient reellement."""
        return self.witness.run(command, timeout=30)

    def mode(self, path):
        result = self.sh("stat -c '%a %U %G' -- " + shlex.quote(path))
        assert result.ok, result.stdout
        return result.stdout.strip()

    def absent(self, path):
        assert not self.sh("test -e " + shlex.quote(path)).ok, path + " ne devrait pas exister"

    def private(self):
        expected = "2700 {} {}".format(self.login, self.project)
        observed = self.mode(self.personal)
        assert observed == expected, "dossier personnel : {} au lieu de {}".format(observed, expected)

    async def file_rule(self):
        print("Regle d'ecriture et creation du dossier prive", flush=True)
        name = self.tag + ".txt"
        for path in (self.root + "/" + name, self.root + "/" + self.tag + "-dir/" + name):
            await self.refused("file_create", "ecriture refusee", path=path, content="non")
            self.absent(path)
        self.ok("file_create refuse la racine et un nouveau dossier")
        others = self.sh("find {} -mindepth 1 -maxdepth 1 -type d ! -user {} ! -name 'chps*' ! -name maqao | head -1"
                         .format(shlex.quote(self.root), shlex.quote(self.login))).stdout.strip()
        if others:
            target = others + "/" + name
            await self.refused("file_create", "ecriture refusee", path=target, content="non")
            self.absent(target)
            self.ok("file_create refuse le dossier d'un autre compte : " + others)
        target = self.personal + "/" + name
        await self.allowed("file_create", path=target, content="premier\n")
        self.private()
        self.ok("file_create cree et ferme le dossier personnel : " + self.mode(self.personal))
        read = await self.allowed("read_remote_file", path=target)
        assert read["content"] == "premier\n"
        listing = await self.allowed("list_dir", path=self.root)
        assert any(entry["name"] == self.login for entry in listing["entries"])
        self.ok("lecture du fichier et de la racine du projet")
        assert self.sh("chmod 755 -- " + shlex.quote(self.personal)).ok
        assert self.mode(self.personal).startswith("2755 ")
        await self.allowed("file_replace", path=target, content="second\n")
        self.private()
        self.ok("un dossier rouvert est referme avant l'ecriture suivante")

    async def course_rule(self):
        print("Cours : lecture partout, travail dans le dossier personnel", flush=True)
        self.course = self.sh("find {} -mindepth 1 -maxdepth 1 -type d \\( -name 'chps*' -o -name maqao \\) | sort | head -1"
                              .format(shlex.quote(self.root))).stdout.strip()
        if not self.course:
            print("  --  aucun dossier de cours dans ce projet", flush=True)
            return
        name = posixpath.basename(self.course)
        await self.allowed("list_dir", path=self.course)
        self.ok("lecture de " + self.course)
        forbidden = "{}/{}.txt".format(self.course, self.tag)
        copy = "{}/{}/{}/{}.txt".format(self.personal, self.tag, name, self.tag)
        payload = await self.refused("file_create", "ecriture refusee", path=forbidden, content="non")
        assert "{}/{}/{}.txt".format(self.personal, name, self.tag) in payload["error"], payload["error"]
        self.absent(forbidden)
        await self.allowed("file_create", path=copy, content="note de cours\n")
        assert (await self.allowed("read_remote_file", path=copy))["content"] == "note de cours\n"
        self.private()
        self.ok("ecriture refusee dans le cours, sous-dossiers crees dans le dossier personnel")

    async def login_commands(self):
        print("Commandes du login", flush=True)
        target = self.personal + "/" + self.tag + ".txt"
        for command, needle in (("rm " + target, "commande refusee"), ("rm -rf " + self.personal, "commande refusee"),
                                ("chmod 777 " + self.personal, "commande refusee"),
                                ("chown {} {}".format(self.login, target), "commande refusee"),
                                ("find {} -name '{}*' -delete".format(self.personal, self.tag), "commande refusee"),
                                ("touch {}/{}".format(self.root, self.tag), "ecriture refusee"),
                                ("echo x > {}/{}".format(self.root, self.tag), "ecriture refusee"),
                                ("cd {} && touch {}".format(self.root, self.tag), "ecriture refusee"),
                                ("mv {} {}/{}".format(target, self.root, self.tag), "ecriture refusee")):
            payload = await self.refused("login_command_run", needle, command=command)
            assert payload.get("refused") is True, command
        self.sh("test -f " + shlex.quote(target)).check("fichier du test conserve")
        self.private()
        self.absent(self.root + "/" + self.tag)
        self.ok("rm, chmod, chown, find -delete, touch, redirection et mv refuses ; rien n'a change")
        await self.allowed("login_command_run", command="mkdir -p {}/{}/sous".format(self.personal, self.tag))
        await self.allowed("login_command_run", command="mv -n {0}.txt {0}/sous/".format(self.tag), cwd=self.personal)
        self.sh("test -f {}/{}/sous/{}.txt".format(shlex.quote(self.personal), self.tag, self.tag)).check("deplacement")
        self.ok("mkdir et mv -n fonctionnent dans le dossier personnel")
        await self.allowed("login_command_run", command="ls -ld " + self.personal)
        self.ok("une commande de lecture reste possible")

    async def transfers(self):
        print("Transferts reels", flush=True)
        work = self.personal + "/" + self.tag
        with tempfile.TemporaryDirectory() as temp:
            local = Path(temp) / "source.txt"
            local.write_text("contenu reel " + self.tag + "\n", encoding="utf-8", newline="\n")
            digest = hashlib.sha256(local.read_bytes()).hexdigest()
            await self.refused("upload_to_romeo", "ecriture refusee", local_path=str(local),
                               remote_path=self.root + "/" + self.tag + ".up")
            self.absent(self.root + "/" + self.tag + ".up")
            await self.allowed("upload_to_romeo", local_path=str(local), remote_path=work + "/envoi.txt")
            seen = self.sh("sha256sum -- " + shlex.quote(work + "/envoi.txt")).stdout.split()[0]
            assert seen == digest
            self.ok("upload_to_romeo : racine refusee, dossier personnel avec empreinte exacte")
            await self.refused("transfer_prepare", "ecriture refusee", direction="upload", local_path=str(local),
                               remote_path=self.root + "/" + self.tag + ".tr")
            plan = await self.allowed("transfer_prepare", direction="upload", local_path=str(local),
                                      remote_path=work + "/transfert.txt")
            await self.allowed("transfer_start", transfer_id=plan["transfer_id"], confirm=True)
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                status = await self.call("transfer_status", transfer_id=plan["transfer_id"])
                if status.get("state") in {"completed", "failed", "cancelled", "interrupted"}:
                    break
                await asyncio.sleep(2)
            assert status.get("state") == "completed", json.dumps(status)[:800]
            seen = self.sh("sha256sum -- " + shlex.quote(work + "/transfert.txt")).stdout.split()[0]
            assert seen == digest
            self.ok("transfer_start : racine refusee, dossier personnel avec empreinte exacte")
        self.private()

    async def job(self):
        print("Job Slurm reel", flush=True)
        course = shlex.quote(self.course) if self.course else "/tmp"
        spec = dict(name=self.tag, command="echo ESPACE_PROJET_OK; id -gn; ls {} > lecture.txt; touch produit.txt".format(course),
                    arch="x64cpu", nodes=1, cpus_per_task=1, mem_gb=1, time_limit="1m")
        await self.refused("job_prepare", "ecriture refusee", workdir=self.root, **spec)
        await self.refused("job_prepare", "ecriture refusee", workdir=self.root + "/" + self.tag, **spec)
        if self.course:
            await self.refused("job_prepare", "ecriture refusee", workdir=self.course + "/" + self.tag, **spec)
        await self.refused("python_env_prepare", "ecriture refusee", env_path=self.root + "/" + self.tag + "-venv",
                           arch="x64cpu", spack_packages=["python@3.11"])
        self.ok("job_prepare et python_env_prepare refusent la racine et le cours")
        workdir = "{}/{}/{}/job".format(self.personal, self.tag, posixpath.basename(self.course) if self.course else "autre")
        plan = await self.allowed("job_prepare", workdir=workdir, **spec)
        submitted = await self.allowed("job_submit", plan_id=plan["plan_id"], confirm=True)
        job_id = submitted["job_id"]
        print("  ..  job {} soumis".format(job_id), flush=True)
        deadline = time.monotonic() + 600
        state = None
        while time.monotonic() < deadline:
            state = (await self.allowed("job_status", job_id=job_id)).get("state")
            if state in {"COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "NODE_FAIL", "OUT_OF_MEMORY"}:
                break
            await asyncio.sleep(5)
        logs = await self.call("job_log_tail", job_id=job_id, lines=50)
        assert state == "COMPLETED", "etat {} : {}".format(state, json.dumps(logs)[:1500])
        assert "ESPACE_PROJET_OK" in json.dumps(logs), json.dumps(logs)[:1500]
        self.sh("test -f " + shlex.quote(workdir + "/lecture.txt")).check("lecture du cours par le job")
        produced = self.mode(workdir + "/produit.txt")
        assert produced.endswith(" {} {}".format(self.login, self.project)), produced
        self.private()
        self.ok("job {} termine dans le dossier prive ; fichier produit : {}".format(job_id, produced))

    async def foreign_folder(self):
        print("Dossier du login appartenant a un autre compte", flush=True)
        folder = "/project/{}/{}".format(self.foreign, self.login)
        before = self.mode(folder)
        assert before.split()[1] != self.login, "ce dossier appartient au login : choisir un autre projet"
        target = folder + "/" + self.tag + ".txt"
        payload = await self.refused("file_create", "proprietaire " + before.split()[1], path=target, content="non")
        self.absent(target)
        plan = await self.allowed("job_prepare", name=self.tag, command="hostname", arch="x64cpu", cpus_per_task=1,
                                  mem_gb=1, time_limit="1m", workdir=folder + "/" + self.tag)
        refused = await self.refused("job_submit", "proprietaire " + before.split()[1], plan_id=plan["plan_id"], confirm=True)
        assert refused.get("submitted") is False
        payload = await self.refused("login_command_run", "proprietaire " + before.split()[1],
                                     command="touch " + target)
        assert payload.get("refused") is True
        self.absent(target)
        assert self.mode(folder) == before
        self.ok("file_create, job_submit et login_command_run refuses et nommes ; dossier inchange : " + before)

    def other_account_denied(self):
        print("Refus reel pour un autre compte du projet (GPFS)", flush=True)
        found = self.sh("find {} -mindepth 2 -maxdepth 2 -type d ! -user {} -perm 2700 2>/dev/null | head -1"
                        .format(shlex.quote(self.root), shlex.quote(self.login))).stdout.strip()
        if not found:
            print("  --  aucun dossier 2700 d'un autre compte a sonder dans ce projet", flush=True)
            return
        assert self.project in self.sh("id -Gn").stdout.split()
        denied = self.sh("ls -- " + shlex.quote(found))
        assert not denied.ok and "Permission denied" in denied.stdout, denied.stdout
        self.ok("membre du groupe {} refuse sur {} ({})".format(self.project, found, self.mode(found)))

    def clean(self):
        # Uniquement les elements portant l'identifiant unique de ce test.
        if self.tag.startswith("mcp-essai-") and len(self.tag) == 20:
            self.sh("rm -rf -- {0}/{1} {0}/{1}.txt".format(shlex.quote(self.personal), self.tag))


async def run(args):
    witness = RomeoSession(host=setting("ROMEO_HOST", "romeo1"))
    with tempfile.TemporaryDirectory() as temp:
        env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONIOENCODING": "utf-8", "ROMEO_TOOL_PROFILE": "expert",
               "ROMEO_UPDATE_CHECK": "0", "ROMEO_MCP_DB": str(Path(temp) / "jobs.db")}
        env.pop("ROMEO_PROJECT_DIRS", None)
        params = StdioServerParameters(command=sys.executable, args=["-m", "romeo_mcp", "serve"], env=env)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                essai = Essai(client, witness, args.project, args.foreign_project)
                print("Login {} ; dossier {}".format(essai.login, essai.personal), flush=True)
                try:
                    await essai.file_rule()
                    await essai.course_rule()
                    await essai.login_commands()
                    await essai.transfers()
                    await essai.job()
                    if args.foreign_project:
                        await essai.foreign_folder()
                    essai.other_account_denied()
                finally:
                    essai.clean()
                essai.private()
                essai.absent(essai.personal + "/" + essai.tag)
                print("{} verifications reelles reussies ; elements de test retires.".format(essai.count), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=os.environ.get("ROMEO_TEST_PROJECT") or setting("ROMEO_ACCOUNT"))
    parser.add_argument("--foreign-project", default=os.environ.get("ROMEO_TEST_FOREIGN_PROJECT", ""))
    args = parser.parse_args()
    if not args.project:
        parser.error("indiquer --project ou ROMEO_TEST_PROJECT")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
