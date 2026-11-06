"""Test reel de la chaine de mise a jour : GitHub, Sigstore, PyPI et pip, sans cluster.

Aucune publication. La verification positive porte sur une vraie attestation
publique (GitHub CLI), avec le meme code que pour ROMEO MCP. Une attestation de ce
depot n'existe qu'apres une release reelle : `--tag vX.Y.Z` la verifie alors.

Usage :
    python tests/smoke_update_chain_live.py [--tag vX.Y.Z]
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from romeo_mcp import __version__, updates as u  # noqa: E402
from tools.prepare_release import REQUIRED_LOCKS, lock_problem  # noqa: E402

#: Artefact public et immuable : gh 2.103.3, Linux amd64, attestation SLSA reelle.
PUBLIC = {"repository": "cli/cli", "workflow": ".github/workflows/deployment.yml", "ref": "refs/heads/trunk",
          "digest": "4c806978ffce1cec70853302a56d70ac6da4f19bae7adca4e1a8ab00633dd91d",
          "subject": "gh_2.103.3_linux_amd64.tar.gz"}
TAG = ""


def run(command, **kwargs):
    return subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=600, **kwargs)


def build_wheel(destination: Path) -> Path:
    # Copie sans .venv ni .git : la wheel provient des sources de travail.
    source = destination / "source"
    shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns(".git", ".venv", "dist", "build", "*.egg-info",
                                                               "__pycache__", "target"))
    command = (["uv", "build", "--wheel", "--out-dir", str(destination)] if shutil.which("uv")
               else [sys.executable, "-m", "build", "--wheel", "--outdir", str(destination)])
    result = run(command, cwd=source)
    assert result.returncode == 0, result.stderr[-2000:]
    return next(destination.glob("romeo_mcp-*.whl"))


class RealChain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        package = cls.root / "origin" / "romeo_mcp"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text('__version__ = "1.0.0"\n', encoding="utf-8")
        (package / "documentation").mkdir()
        (package / "documentation/manifest.json").write_text("{}", encoding="utf-8")
        cls.target = u.Installation(Path(sys.executable), package, cls.root / "updates")
        cls.target.root.mkdir(parents=True)
        cls.wheel = build_wheel(cls.root / "wheel")

    def public_bundles(self):
        return u.attestation_bundles(PUBLIC["digest"], PUBLIC["repository"])

    def check_script(self, digest, identity, files):
        python = u.verifier_python(self.target)
        return run([str(python), "-I", str(ROOT / "romeo_mcp/attestation_check.py"), "--digest", digest,
                    "--identity", identity, *map(str, files)])

    def release_of(self, tag):
        """Metadonnees reelles d'une release publiee, sous la forme de latest_release."""
        with u._request(f"https://api.github.com/repos/{u.REPOSITORY}/releases/tags/{tag}") as response:
            value = json.loads(response.read())
        version = tag[1:]
        name = f"romeo_mcp-{version}-py3-none-any.whl"
        asset = next(item for item in value["assets"] if item["name"] == name)
        return {"version": version, "tag": tag, "name": name, "sha256": asset["digest"][7:], "size": asset["size"],
                "url": f"https://github.com/{u.REPOSITORY}/releases/download/{tag}/{name}", "notes": "",
                "page": f"https://github.com/{u.REPOSITORY}/releases/tag/{tag}"}

    def test_1_real_release_is_read_and_tampered_digest_refused(self):
        release = u.latest_release()
        self.assertIsNotNone(release)
        u.validate_release(release)
        wheel = self.root / "telechargee.whl"
        u._download(release, wheel)
        self.assertEqual(hashlib.sha256(wheel.read_bytes()).hexdigest(), release["sha256"])
        self.assertTrue(zipfile.is_zipfile(wheel))
        flipped = ("0" if release["sha256"][0] != "0" else "1") + release["sha256"][1:]
        with self.assertRaisesRegex(u.UpdateError, "empreinte"):
            u._download({**release, "sha256": flipped}, self.root / "falsifiee.whl")

    def test_2_verifier_comes_from_the_hash_lock(self):
        python = u.verifier_python(self.target)
        frozen = run([str(python), "-I", "-m", "pip", "freeze"]).stdout.lower().replace("_", "-")
        lock = (u.LOCKS / "verifier.lock").read_text(encoding="utf-8").lower()
        installed = [line for line in frozen.splitlines() if "==" in line]
        self.assertTrue(any(line.startswith("sigstore==") for line in installed), frozen)
        for line in installed:
            self.assertIn(line, lock)
        again = u.verifier_python(self.target)
        self.assertEqual(python, again)

    def test_3_real_attestation_is_accepted(self):
        result = u.verify_attestation(self.target, PUBLIC["digest"], PUBLIC["ref"],
                                      repository=PUBLIC["repository"], workflow=PUBLIC["workflow"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["subject"], PUBLIC["subject"])
        self.assertEqual(result["predicate_type"], "https://slsa.dev/provenance/v1")

    def test_4_real_attestation_with_any_other_identity_is_refused(self):
        for repository, workflow, ref in ((PUBLIC["repository"], ".github/workflows/autre.yml", PUBLIC["ref"]),
                                          (PUBLIC["repository"], PUBLIC["workflow"], "refs/tags/v2.103.3")):
            with self.subTest(workflow=workflow, ref=ref), self.assertRaisesRegex(u.UpdateError, "Attestation Sigstore refusee"):
                u.verify_attestation(self.target, PUBLIC["digest"], ref, repository=repository, workflow=workflow)
        # Une attestation d'un autre depot ne peut pas valider une release de ROMEO MCP.
        files = self.write_bundles(self.public_bundles())
        identity = f"https://github.com/{u.REPOSITORY}/{u.RELEASE_WORKFLOW}@refs/tags/v9.9.9"
        self.assertEqual(self.check_script(PUBLIC["digest"], identity, files).returncode, 1)

    def write_bundles(self, bundles, prefix="bundle"):
        files = []
        for index, data in enumerate(bundles):
            path = self.root / f"{prefix}-{index}"
            path.write_bytes(data)
            files.append(path)
        return files

    def test_5_altered_digest_payload_or_signature_is_refused(self):
        identity = f"https://github.com/{PUBLIC['repository']}/{PUBLIC['workflow']}@{PUBLIC['ref']}"
        bundles = self.public_bundles()
        other = ("0" if PUBLIC["digest"][0] != "0" else "1") + PUBLIC["digest"][1:]
        self.assertEqual(self.check_script(other, identity, self.write_bundles(bundles)).returncode, 1)
        decoded = None
        spec = run([str(u.verifier_python(self.target)), "-I", "-c",
                    "import sys, runpy, base64; m = runpy.run_path(sys.argv[1]);"
                    "print(base64.b64encode(m['decode_snappy'](open(sys.argv[2], 'rb').read())).decode())",
                    str(ROOT / "romeo_mcp/attestation_check.py"), str(self.write_bundles(bundles, "brut")[-1])])
        self.assertEqual(spec.returncode, 0, spec.stderr)
        decoded = json.loads(base64.b64decode(spec.stdout))
        self.assertEqual(self.check_script(PUBLIC["digest"], identity,
                                           self.write_bundles([json.dumps(decoded).encode()], "intact")).returncode, 0)
        payload = json.loads(base64.b64decode(decoded["dsseEnvelope"]["payload"]))
        payload["subject"][0]["digest"]["sha256"] = "f" * 64
        altered = {**decoded, "dsseEnvelope": {**decoded["dsseEnvelope"],
                                                "payload": base64.b64encode(json.dumps(payload).encode()).decode()}}
        signature = bytearray(base64.b64decode(decoded["dsseEnvelope"]["signatures"][0]["sig"]))
        signature[10] ^= 0xff
        forged = {**decoded, "dsseEnvelope": {**decoded["dsseEnvelope"], "signatures": [
            {**decoded["dsseEnvelope"]["signatures"][0], "sig": base64.b64encode(bytes(signature)).decode()}]}}
        for label, value in (("contenu altere", altered), ("signature alteree", forged)):
            with self.subTest(label):
                result = self.check_script(PUBLIC["digest"], identity, self.write_bundles([json.dumps(value).encode()], label[:3]))
                self.assertEqual(result.returncode, 1, result.stdout)

    def test_6_release_without_attestation_is_refused_end_to_end(self):
        release = self.release_of("v1.4.0")
        before = self.target.state()
        with self.assertRaisesRegex(u.UpdateError, "Aucune attestation"):
            u.apply_release(self.target, release, before)
        self.assertEqual(self.target.state(), before)
        self.assertEqual(list((self.target.root / "versions").iterdir()), [])
        self.assertFalse((self.target.root / "state.json").exists())

    def test_7_built_wheel_carries_complete_locks(self):
        with zipfile.ZipFile(self.wheel) as archive:
            for name, package in REQUIRED_LOCKS.items():
                self.assertIsNone(lock_problem(archive.read(name).decode(), package), name)
            self.assertIn("romeo_mcp/attestation_check.py", archive.namelist())
        extracted = u.extract_wheel_lock(self.wheel, self.root / "extrait.lock")
        self.assertIn("mcp==", extracted.read_text(encoding="utf-8"))
        with self.assertRaisesRegex(u.UpdateError, "sans verrou"):
            bare = self.root / "sans-verrou.whl"
            with zipfile.ZipFile(bare, "w") as archive:
                archive.writestr("romeo_mcp/__init__.py", "")
            u.extract_wheel_lock(bare, self.root / "absent.lock")

    def test_8_altered_lock_is_refused_by_real_pip(self):
        environment = self.root / "venv-faux-verrou"
        run([sys.executable, "-I", "-m", "venv", str(environment)]).check_returncode()
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        lines = (u.LOCKS / "server.lock").read_text(encoding="utf-8")
        altered = self.root / "altere.lock"
        import re
        altered.write_text(re.sub(r"--hash=sha256:[0-9a-f]{64}", "--hash=sha256:" + "0" * 64, lines), encoding="utf-8")
        with self.assertRaisesRegex(u.UpdateError, "(?i)hash"):
            u.install_locked(python, altered)
        frozen = run([str(python), "-I", "-m", "pip", "freeze"]).stdout
        self.assertNotIn("mcp==", frozen)

    def test_9_real_install_selection_dispatch_and_server(self):
        """Tout est reel sauf l'attestation, qui n'existe pas avant la release."""
        data = self.wheel.read_bytes()
        name = f"romeo_mcp-{__version__}-py3-none-any.whl"
        release = {"version": __version__, "tag": "v" + __version__, "name": name, "sha256": hashlib.sha256(data).hexdigest(),
                   "size": len(data), "url": f"https://github.com/{u.REPOSITORY}/releases/download/v{__version__}/{name}",
                   "page": f"https://github.com/{u.REPOSITORY}/releases/tag/v{__version__}", "notes": ""}
        phases = []
        with patch.object(u, "_download", side_effect=lambda rel, path: shutil.copyfile(self.wheel, path)), \
                patch.object(u, "verify_attestation", return_value={"ok": True, "simulee": True}) as attestation:
            outcome = u.apply_release(self.target, release, self.target.state(), progress=phases.append)
        attestation.assert_called_once_with(self.target, release["sha256"], "refs/tags/v" + __version__)
        self.assertEqual(phases, ["download", "attestation", "environment", "install", "verify", "select"])
        slot = outcome["active"]
        self.assertEqual(self.target.state()["active"], slot)
        python = self.target.executable(slot)
        frozen = run([str(python), "-I", "-m", "pip", "freeze"]).stdout.lower().replace("_", "-").splitlines()
        lock = (u.LOCKS / "server.lock").read_text(encoding="utf-8").lower()
        pinned = [line for line in frozen if "==" in line]
        self.assertTrue(any(line.startswith("mcp==") for line in pinned), frozen)
        for line in pinned:
            self.assertIn(line, lock)
        self.assertEqual(run([str(python), "-I", "-m", "pip", "check"]).returncode, 0)
        env = {**os.environ, "ROMEO_UPDATES_DIR": str(self.root / "updates-parent"), "ROMEO_UPDATE_CHECK": "0",
               "ROMEO_MCP_DB": str(self.root / "jobs.db"), "ROMEO_CONFIG": str(self.root / "absente.json"),
               "ROMEO_TOOL_PROFILE": "expert", "PYTHONIOENCODING": "utf-8", u.ORIGIN_ENV: "", u.DISPATCH_ENV: "1"}
        env.pop("PYTHONPATH", None)
        from mcp import ClientSession, StdioServerParameters, stdio_client

        async def exercise():
            params = StdioServerParameters(command=str(python), args=["-I", "-m", "romeo_mcp", "serve"], env=env, cwd=str(self.root))
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as client:
                    init = await client.initialize()
                    names = {tool.name for tool in (await client.list_tools()).tools}
                    return init.instructions, names, (await client.call_tool("mcp_update_status", {}))
        instructions, names, status = asyncio.run(exercise())
        self.assertLess(instructions.index("- Espaces projet"), 200)
        self.assertIn("python -m romeo_mcp update", instructions)
        for removed in ("mcp_update_start", "mcp_update_policy", "mcp_update_rollback"):
            self.assertNotIn(removed, names)
            self.assertNotIn(removed, instructions)
        self.assertEqual(json.loads(status.content[0].text)["running_version"], __version__)

    @unittest.skipUnless(TAG, "indiquer --tag apres une release attestee")
    def test_a_published_release_passes_every_check(self):
        release = self.release_of(TAG)
        result = u.verify_attestation(self.target, release["sha256"], "refs/tags/" + TAG)
        self.assertEqual(result["identity"], f"https://github.com/{u.REPOSITORY}/{u.RELEASE_WORKFLOW}@refs/tags/{TAG}")
        outcome = u.apply_release(self.target, release, self.target.state())
        self.assertEqual(outcome["version"], TAG[1:])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--tag", default="")
    known, remaining = parser.parse_known_args()
    TAG = known.tag
    RealChain.test_a_published_release_passes_every_check.__unittest_skip__ = not TAG
    unittest.main(argv=[sys.argv[0], *remaining], verbosity=2)
