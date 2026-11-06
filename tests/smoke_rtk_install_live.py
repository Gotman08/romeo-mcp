"""Test reel sur ROMEO : vrai serveur MCP, SSH, GitHub et GPFS, pour un compte sans RTK.

Le compte de test a generalement deja RTK. Chaque scenario lance donc le vrai serveur avec
un HOME et un PATH de test sur le vrai login (`env HOME=... PATH=... /bin/bash -l -s`) : c'est
le seul element modifie. Le telechargement, les empreintes, l'ecriture sur GPFS et
l'execution sont reels.

Tout reste sous `~/mcp-essai-rtk-<id>`, retire a la fin. `~/.local/bin/rtk`, l'historique
RTK et la liste du home du compte sont compares avant et apres. Aucun job n'est soumis.
Le refus d'architecture ne se teste pas ici : le login est toujours en x86_64.

Sous Windows, placer l'OpenSSH du systeme en tete du PATH :
    export PATH="/c/Windows/System32/OpenSSH:$PATH"

Usage :
    python tests/smoke_rtk_install_live.py
"""
from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import json
import os
from pathlib import Path
import posixpath
import shlex
import sys
import tempfile
from types import SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mcp import ClientSession, StdioServerParameters, stdio_client  # noqa: E402
from romeo_mcp import rtk  # noqa: E402
from romeo_mcp.config import setting  # noqa: E402
from romeo_mcp.ssh import RomeoSession, session  # noqa: E402

PIN = rtk.PINNED
PREFIX = "mcp-essai-rtk-"
#: Un proxy ferme fait echouer le vrai curl du vrai script, sans toucher au code.
PANNE = "https_proxy=http://127.0.0.1:9 HTTPS_PROXY=http://127.0.0.1:9"
BOOTSTRAP = ("import sys\n"
             "from romeo_mcp import ssh\n"
             "ssh._REMOTE_SHELL = sys.argv[1]\n"
             "from romeo_mcp.server import main\n"
             "main()\n")


async def call(client, tool, **arguments):
    result = await client.call_tool(tool, arguments)
    return json.loads(result.content[0].text)


async def allowed(client, tool, **arguments):
    payload = await call(client, tool, **arguments)
    assert payload.get("ok") is True, "{} refuse : {}".format(tool, json.dumps(payload)[:900])
    return payload


class Essai:
    def __init__(self, witness, temp):
        self.witness, self.temp = witness, temp
        self.tag = PREFIX + uuid.uuid4().hex[:10]
        self.root = "{}/{}".format(witness.home, self.tag)
        self.count = 0

    def ok(self, label):
        self.count += 1
        print("  OK  " + label, flush=True)

    @contextlib.asynccontextmanager
    async def serveur(self, home=None, remote_env="", auto="1"):
        env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONIOENCODING": "utf-8", "ROMEO_TOOL_PROFILE": "expert",
               "ROMEO_UPDATE_CHECK": "0", "ROMEO_MCP_DB": str(Path(self.temp) / "jobs.db"),
               "ROMEO_CONCURRENCY_ROOT": str(Path(self.temp) / "concurrency"), "ROMEO_RTK_AUTO_INSTALL": auto}
        arguments = ["-m", "romeo_mcp", "serve"]
        if home:
            # sshd a deja lu le ~/.bashrc du compte : le PATH herite contiendrait son ~/.local/bin.
            shell = " ".join(("env", "HOME=" + shlex.quote(home), "PATH=/usr/local/bin:/usr/bin:/bin", remote_env,
                              "/bin/bash -l -s"))
            arguments = ["-c", BOOTSTRAP, shell]
        params = StdioServerParameters(command=sys.executable, args=arguments, env=env)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                yield client

    def sh(self, command, timeout=30):
        """Temoin hors MCP : ce que le systeme de fichiers contient reellement."""
        return self.witness.run(command, timeout=timeout)

    def out(self, command):
        result = self.sh(command)
        assert result.ok, "{} : {}".format(command, result.stdout)
        return result.stdout.strip()

    def fake_home(self, name):
        home = "{}/{}".format(self.root, name)
        self.out("mkdir -p -- " + shlex.quote(home))
        return home

    def inventory(self):
        """Ce qui ne doit jamais changer, sauf le dossier de ce test."""
        return self.out('for f in "$HOME/.local/bin/rtk" "$HOME/.local/share/rtk/history.db"; do '
                        'if [ -e "$f" ]; then stat -c "%n %i %s %Y" -- "$f"; sha256sum -- "$f"; else echo "absent $f"; fi; done; '
                        'ls -A "$HOME/.local/bin" 2>/dev/null; echo ---; ls -A "$HOME"')

    def digest(self, path):
        return self.out("sha256sum < {} | cut -d' ' -f1".format(shlex.quote(path)))

    def absent(self, path):
        assert not self.sh("test -e {0} || test -L {0}".format(shlex.quote(path))).ok, path + " ne devrait pas exister"

    def no_leftover(self, home):
        found = self.out("find {} -name '.rtk-install.*' 2>/dev/null | head -5".format(shlex.quote(home)))
        assert not found, "dossier temporaire restant : " + found

    def installed(self, home):
        target = home + "/.local/bin/rtk"
        assert self.digest(target) == PIN.binary_sha256, target
        assert self.out("stat -c '%a %h' -- " + shlex.quote(target)) == "755 1", target
        assert self.out(shlex.quote(target) + " --version") == "rtk " + PIN.version, target
        self.no_leftover(home)

    async def real_account(self):
        print("Compte reel : RTK deja present, rien n'est installe", flush=True)
        if not self.sh('test -e "$HOME/.local/bin/rtk" || type -P rtk >/dev/null').ok:
            print("  --  RTK absent de ce compte : scenario ignore pour ne rien y installer", flush=True)
            return
        async with self.serveur() as client:
            status = await allowed(client, "rtk_status", include_gain=False)
            assert status["available"] is True and "install" not in status, status
            ran = await allowed(client, "login_command_run", command="hostname", use_rtk=True)
            assert ran["rtk"]["reason"] == "not_rewritten" and "install" not in ran["rtk"], ran
        self.ok("rtk_status et use_rtk=true utilisent {} ({}) sans y toucher".format(status["path"], status["version"]))

    async def opt_out(self):
        print("Desactivation", flush=True)
        home = self.fake_home("desactive")
        async with self.serveur(home, auto="0") as client:
            status = await allowed(client, "rtk_status")
            assert status["available"] is False and status["install"]["state"] == "disabled", status
            ran = await allowed(client, "login_command_run", command="hostname", use_rtk=True)
            assert ran["executed_command"] == "hostname" and ran["rtk"]["install"]["state"] == "disabled", ran
        self.absent(home + "/.local")
        self.ok("ROMEO_RTK_AUTO_INSTALL=0 : RTK absent signale, commande brute, rien d'ecrit")

    async def first_command(self):
        print("Premier besoin : login_command_run(use_rtk=true)", flush=True)
        home = self.fake_home("commande")
        repository = home + "/depot"
        self.out("mkdir -p {0} && cd {0} && git init -q . && echo x > f".format(shlex.quote(repository)))
        async with self.serveur(home) as client:
            names = {tool.name for tool in (await client.list_tools()).tools}
            assert "rtk_status" in names and not {"rtk_install", "rtk_install_prepare"} & names, sorted(names)
            self.absent(home + "/.local")
            self.ok("le demarrage du serveur n'a rien installe")
            first = await allowed(client, "login_command_run", command="git status", cwd=repository, use_rtk=True)
            install = first["rtk"]["install"]
            assert install["state"] == "installed" and install["attempted_now"] is True, first
            assert install["path"] == home + "/.local/bin/rtk" and first["rtk"]["path"] == install["path"], first
            assert first["executed_command"] == "rtk git status" and "f" in first["output"], first
            self.installed(home)
            self.ok("installe en {} s, empreinte exacte, mode 755, puis commande reelle via RTK".format(
                install["duration_seconds"]))
            second = await allowed(client, "login_command_run", command="git status", cwd=repository, use_rtk=True)
            assert "install" not in second["rtk"] and second["executed_command"] == "rtk git status", second
            status = await allowed(client, "rtk_status")
            assert status["version"] == "rtk " + PIN.version and "install" not in status, status
            assert isinstance(status["gain"], dict), status
            self.ok("appels suivants : aucune nouvelle installation ; rtk_status lit version et statistiques")
        async with self.serveur(home) as client:
            third = await allowed(client, "login_command_run", command="git status", cwd=repository, use_rtk=True)
            assert "install" not in third["rtk"] and third["rtk"]["reason"] == "rewritten", third
        self.ok("nouveau processus serveur : binaire retrouve, une seule installation par compte")

    async def first_status(self):
        print("Premier besoin : rtk_status", flush=True)
        home = self.fake_home("statut")
        async with self.serveur(home) as client:
            status = await allowed(client, "rtk_status")
            assert status["available"] is True and status["install"]["state"] == "installed", status
            assert status["version"] == "rtk " + PIN.version and isinstance(status["gain"], dict), status
        self.installed(home)
        self.ok("rtk_status installe puis lit le binaire")

    async def parallel(self):
        print("Besoins simultanes", flush=True)
        home = self.fake_home("parallele")
        async with self.serveur(home) as client:
            results = await asyncio.gather(*(allowed(client, "login_command_run", command="hostname", use_rtk=True)
                                             for _ in range(3)))
        attempts = [r["rtk"]["install"] for r in results if r["rtk"].get("install", {}).get("attempted_now")]
        assert len(attempts) == 1 and attempts[0]["state"] == "installed", results
        assert all(r["executed_command"] == "hostname" for r in results), results
        self.installed(home)
        self.ok("trois appels simultanes : une seule installation, trois commandes executees")

    async def download_failure(self):
        print("Panne reelle du telechargement", flush=True)
        home = self.fake_home("panne")
        async with self.serveur(home, PANNE) as client:
            first = await allowed(client, "login_command_run", command="hostname", use_rtk=True)
            install = first["rtk"]["install"]
            assert first["executed_command"] == "hostname" and first["rtk"]["reason"] == "not_installed", first
            assert install["state"] == "failed" and install["exit_code"] == 13, first
            assert install["attempted_now"] is True and install["detail"].startswith("curl "), first
            self.ok("commande executee en mode brut, echec signale : " + install["detail"])
            second = await allowed(client, "login_command_run", command="hostname", use_rtk=True)
            assert second["rtk"]["install"]["attempted_now"] is False, second
            status = await allowed(client, "rtk_status")
            assert status["available"] is False and status["install"]["attempted_now"] is False, status
            self.ok("aucune nouvelle tentative dans ce processus ; rtk_status rappelle l'echec")
        self.absent(home + "/.local/bin/rtk")
        self.no_leftover(home)
        self.ok("rien n'est laisse sur le compte")
        async with self.serveur(home) as client:
            recovered = await allowed(client, "rtk_status", include_gain=False)
            assert recovered["install"]["state"] == "installed", recovered
        self.installed(home)
        self.ok("reseau revenu, nouveau processus serveur : installation reussie")

    async def existing_kept(self):
        print("Fichier deja present", flush=True)
        for name, label, prepare in (
                ("fichier", "fichier non executable", lambda t: self.witness.write_file(t, "garde\n", mode="644")),
                ("lien", "lien casse", lambda t: self.out("mkdir -p -- {0} && ln -s /inexistant/rtk {1}".format(
                    shlex.quote(posixpath.dirname(t)), shlex.quote(t))))):
            home = self.fake_home(name)
            target = home + "/.local/bin/rtk"
            prepare(target)
            before = self.out("stat -c '%F %s %Y' -- " + shlex.quote(target))
            async with self.serveur(home) as client:
                ran = await allowed(client, "login_command_run", command="hostname", use_rtk=True)
            assert ran["executed_command"] == "hostname", ran
            assert ran["rtk"]["install"]["state"] == "failed" and ran["rtk"]["install"]["exit_code"] == 12, ran
            assert self.out("stat -c '%F %s %Y' -- " + shlex.quote(target)) == before, label
            self.no_leftover(home)
            self.ok("{} : pas remplace, commande brute, code 12".format(label))
        home = self.fake_home("executable")
        target = home + "/.local/bin/rtk"
        self.witness.write_file(target, '#!/bin/sh\necho "rtk 9.9.9"\n', mode="755")
        before = self.digest(target)
        async with self.serveur(home) as client:
            status = await allowed(client, "rtk_status", include_gain=False)
        assert status["version"] == "rtk 9.9.9" and "install" not in status, status
        assert self.digest(target) == before
        self.ok("autre version deja installee : utilisee telle quelle, pas remplacee")

    async def outside_home(self):
        print("Rien hors du home", flush=True)
        home = self.fake_home("sortie")
        outside = "/tmp/" + self.tag
        self.out("ln -s {} {}/.local".format(shlex.quote(outside), shlex.quote(home)))
        async with self.serveur(home) as client:
            ran = await allowed(client, "login_command_run", command="hostname", use_rtk=True)
        assert ran["rtk"]["install"]["exit_code"] == 11 and ran["executed_command"] == "hostname", ran
        self.absent(outside)
        self.no_leftover(home)
        self.ok("~/.local lie vers /tmp : refus, rien d'ecrit hors du home, commande brute")

    def altered_release(self):
        print("Refus reels du script : vrai telechargement, valeurs alterees", flush=True)
        home = self.fake_home("alteree")
        target = home + "/.local/bin/rtk"
        script = lambda **changes: rtk.install_script(home, dataclasses.replace(PIN, **changes))  # noqa: E731
        for text, code, label in (
                (script(archive_sha256="0" * 64), 14, "empreinte d'archive differente"),
                (script(archive_size=PIN.archive_size - 1), 14, "archive plus grande que l'epingle"),
                (script(archive_size=PIN.archive_size + 1), 14, "archive plus petite que l'epingle"),
                (script(asset="absent-" + self.tag + ".tar.gz"), 13, "asset introuvable"),
                (script(binary_sha256="0" * 64), 15, "empreinte de binaire differente"),
                (script().replace("version={}\n".format(PIN.version), "version=0.0.0\n"), 15, "version differente")):
            result = self.sh(text, timeout=60)
            assert result.rc == code, "{} : rc {} {}".format(label, result.rc, result.stdout)
            assert "RTK_INSTALL_FAILED" in result.stdout, result.stdout
            self.absent(target)
            self.no_leftover(home)
            self.ok("{} : code {}, rien d'installe, aucun reste".format(label, result.rc))
        reported = rtk.attempt(SimpleNamespace(host=self.witness.host, user=self.witness.user, home=home),
                               dataclasses.replace(PIN, archive_sha256="0" * 64))
        assert reported["state"] == "failed" and reported["exit_code"] == 14, reported
        assert "differe de l'epingle" in reported["error"] and reported["detail"].startswith("sha256 "), reported
        self.ok("un echec reel est rendu au modele avec sa cause : " + reported["detail"][:24] + "...")

    def clean(self):
        # Uniquement le dossier portant l'identifiant unique de ce test.
        if self.tag.startswith(PREFIX) and len(self.tag) == len(PREFIX) + 10:
            self.sh("rm -rf -- " + shlex.quote(self.root))


async def run():
    witness = RomeoSession(host=setting("ROMEO_HOST", "romeo1"))
    with tempfile.TemporaryDirectory() as temp:
        essai = Essai(witness, temp)
        print("Compte {} ; dossier de test {}".format(witness.user, essai.root), flush=True)
        before = essai.inventory()
        try:
            await essai.real_account()
            await essai.opt_out()
            await essai.first_command()
            await essai.first_status()
            await essai.parallel()
            await essai.download_failure()
            await essai.existing_kept()
            await essai.outside_home()
            essai.altered_release()
        finally:
            essai.clean()
        essai.absent(essai.root)
        after = essai.inventory()
        assert after == before, "le compte a change :\n{}\n---\n{}".format(before, after)
        print("{} verifications reelles reussies ; {} retire, ~/.local/bin et l'historique RTK inchanges."
              .format(essai.count, essai.root), flush=True)
    witness.close()
    session(longue=True).close()


if __name__ == "__main__":
    asyncio.run(run())
