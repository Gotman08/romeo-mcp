"""Mises a jour hors reseau : integrite, consentement et vrais processus isoles."""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import base64
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from romeo_mcp import updates as u


def release_payload(data=b"wheel", version="9.0.0"):
    name = f"romeo_mcp-{version}-py3-none-any.whl"
    return {"tag_name": "v" + version, "draft": False, "prerelease": False, "body": "Notes",
            "assets": [{"name": name, "state": "uploaded", "size": len(data),
                        "digest": "sha256:" + hashlib.sha256(data).hexdigest(),
                        "browser_download_url": f"https://github.com/{u.REPOSITORY}/releases/download/v{version}/{name}"}]}


def release(data=b"wheel"):
    with patch.object(u, "_request", return_value=io.BytesIO(json.dumps(release_payload(data)).encode())):
        return u.latest_release()


class TemporaryInstallation(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.package = self.root / "source" / "romeo_mcp"
        self.package.mkdir(parents=True)
        (self.package / "__init__.py").write_text('__version__ = "1.0.0"\n', encoding="utf-8")
        (self.package / "server.py").write_text("server = object()\n", encoding="utf-8")
        docs = self.package / "documentation"
        docs.mkdir()
        (docs / "page.md").write_bytes(b"Documentation")
        u._write_json(docs / "manifest.json", {"files": {"page.md": hashlib.sha256(b"Documentation").hexdigest()}})
        self.target = u.Installation(Path(sys.executable), self.package, self.root / "updates")
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {u.DISPATCH_ENV: "", u.ORIGIN_ENV: "", "ROMEO_UPDATE_CHECK": "0"}).start()

    def prepared(self):
        slot = "v8.0.0-" + "a" * 12 + "-" + "b" * 8
        self.target.slot_dir(slot).mkdir(parents=True)
        state = {"schema": 1, "active": slot, "previous": None, "can_rollback": True,
                 "base_fingerprint": u._fingerprint(self.package)}
        u._write_json(self.target.root / "state.json", state)
        return state


class ReleaseTests(TemporaryInstallation):
    def test_stable_release_and_numeric_order(self):
        self.assertGreater(u.version_tuple("1.10.0"), u.version_tuple("1.9.9"))
        with patch.object(u, "latest_release", return_value=release()):
            self.assertTrue(u.check()["update_available"])
        for invalid in ("1.0", "1.0.0rc1", "../1.0.0", "v1.0.0"):
            with self.assertRaises(u.UpdateError):
                u.version_tuple(invalid)

    def test_incomplete_or_untrusted_release_rejected(self):
        for change in (lambda p: p.update(draft=True), lambda p: p.update(prerelease=True),
                       lambda p: p.update(tag_name="../../bad"), lambda p: p.update(assets=[]),
                       lambda p: p["assets"].append(p["assets"][0].copy()),
                       lambda p: p["assets"][0].update(digest=None),
                       lambda p: p["assets"][0].update(size=u.MAX_ASSET + 1),
                       lambda p: p["assets"][0].update(browser_download_url="https://example.org/package.whl")):
            payload = release_payload()
            change(payload)
            with patch.object(u, "_request", return_value=io.BytesIO(json.dumps(payload).encode())):
                with self.assertRaises(u.UpdateError):
                    u.latest_release()

    def test_network_absent_and_rate_limited(self):
        with patch.object(u, "_request", side_effect=HTTPError(u.API, 404, "missing", {}, None)):
            self.assertIsNone(u.latest_release())
        for error in (HTTPError(u.API, 403, "limit", {}, None), URLError("offline")):
            with patch.object(u, "_request", side_effect=error):
                with self.assertRaises(u.UpdateError):
                    u.latest_release()

    def test_download_integrity_size_and_redirects(self):
        expected = release(b"good")
        for data in (b"bad!", b"too large", b"go"):
            destination = self.root / ("download-" + str(len(data)))
            with patch.object(u, "_request", return_value=io.BytesIO(data)):
                with self.assertRaises(u.UpdateError):
                    u._download(expected, destination)
        class Response(io.BytesIO):
            def geturl(self):
                return "http://example.org/redirect"
        with patch.object(u, "urlopen", return_value=Response(b"")):
            with self.assertRaisesRegex(u.UpdateError, "Redirection"):
                u._request(u.API)

    def test_state_rejects_paths_and_storage_in_checkout(self):
        u._write_json(self.target.root / "state.json", {"schema": 1, "active": "../private"})
        with self.assertRaises(u.UpdateError):
            self.target.state()
        (self.root / ".git").mkdir()
        with patch.dict(os.environ, ROMEO_UPDATES_DIR=str(self.root / "nested")):
            with self.assertRaisesRegex(u.UpdateError, "hors des depots"):
                u.installation()

    def test_source_guard_clean_dirty_and_unrelated_remote(self):
        def git(*args):
            return subprocess.run(["git", "-C", str(self.package.parent), *args],
                                  capture_output=True, check=True)
        git("init")
        git("remote", "add", "origin", f"https://github.com/{u.REPOSITORY}.git")
        with self.assertRaisesRegex(u.UpdateError, "Modifications locales"):
            u._source_guard(self.target)
        git("add", ".")
        git("-c", "user.name=Test", "-c", "user.email=test@example.org", "commit", "-m", "fixture")
        u._source_guard(self.target)
        git("remote", "set-url", "origin", "https://github.com/example/other.git")
        with self.assertRaisesRegex(u.UpdateError, "officiel"):
            u._source_guard(self.target)


class TransactionTests(TemporaryInstallation):
    def setUp(self):
        super().setUp()
        # L'attestation reelle est couverte par smoke_update_chain_live.py.
        self.attestation = patch.object(u, "verify_attestation", return_value={"ok": True}).start()
        patch.object(u, "extract_wheel_lock", return_value=Path("server.lock")).start()

    def test_failed_install_health_download_or_attestation_preserves_active(self):
        before = self.prepared()
        for stage in ("download", "attestation", "install", "health"):
            with self.subTest(stage=stage), patch.object(u, "_download") as download, \
                 patch.object(u, "_run") as run, patch.object(u, "health_check", return_value="9.0.0") as health:
                failing = {"download": download, "attestation": self.attestation, "install": run, "health": health}[stage]
                failing.side_effect = u.UpdateError("fixture failure")
                with self.assertRaises(u.UpdateError):
                    u.apply_release(self.target, release(), before)
                failing.side_effect = None
                self.assertEqual(self.target.state(), before)
                self.assertEqual(list((self.target.root / "versions").iterdir()), [self.target.slot_dir(before["active"])])
                if stage in {"download", "attestation"}:
                    run.assert_not_called()

    def test_pointer_changed_after_confirmation_rejected(self):
        before = self.target.state()
        self.prepared()
        with patch.object(u, "_download") as download:
            with self.assertRaisesRegex(u.UpdateError, "change"):
                u.apply_release(self.target, release(), before)
            download.assert_not_called()

    def test_health_version_must_match(self):
        with patch.object(u, "_download"), patch.object(u, "_run"), patch.object(u, "health_check", return_value="8.0.0"):
            with self.assertRaisesRegex(u.UpdateError, "differe"):
                u.apply_release(self.target, release(), self.target.state())
        self.assertIsNone(self.target.state()["active"])

    def test_dirty_clone_detected_again_before_commit(self):
        with patch.object(u, "_download"), patch.object(u, "_run"), patch.object(u, "health_check", return_value="9.0.0"), \
             patch.object(u, "_source_guard", side_effect=[None, u.UpdateError("changed")]):
            with self.assertRaisesRegex(u.UpdateError, "changed"):
                u.apply_release(self.target, release(), self.target.state())
        self.assertIsNone(self.target.state()["active"])

    def test_interrupt_after_atomic_activation_keeps_candidate(self):
        write = u._write_json
        def interrupted(path, value):
            write(path, value)
            if path.name == "state.json":
                raise KeyboardInterrupt()
        with patch.object(u, "_download"), patch.object(u, "_run"), patch.object(u, "health_check", return_value="9.0.0"), \
             patch.object(u, "_write_json", side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                u.apply_release(self.target, release(), self.target.state())
        self.assertTrue(self.target.slot_dir(self.target.state()["active"]).is_dir())

    def test_rollback_checks_base_fingerprint_and_health(self):
        before = self.prepared()
        (self.package / "server.py").write_text("modified", encoding="utf-8")
        with self.assertRaisesRegex(u.UpdateError, "origine a change"):
            u.rollback(self.target, before)
        self.assertEqual(self.target.state(), before)

    def test_failed_rollback_health_preserves_pointer(self):
        before = self.prepared()
        with patch.object(u, "health_check", side_effect=u.UpdateError("unhealthy")):
            with self.assertRaises(u.UpdateError):
                u.rollback(self.target, before)
        self.assertEqual(self.target.state(), before)

    def test_lock_contention_and_release(self):
        path = self.root / "lock"
        with u.file_lock(path):
            with self.assertRaises(u.UpdateError):
                with u.file_lock(path):
                    self.fail("second writer")
        with u.file_lock(path):
            pass

    def test_confirmation_and_noninteractive_refusal(self):
        with patch("sys.stdin.isatty", return_value=False):
            with self.assertRaises(u.UpdateError):
                u._confirm(False, "Installer ?")
            self.assertTrue(u._confirm(True, "Installer ?"))
        with patch("sys.stdin.isatty", return_value=True), patch("builtins.input", return_value="non"):
            self.assertFalse(u._confirm(False, "Installer ?"))
        with patch.object(u, "installation", return_value=self.target), patch.object(u, "latest_release", return_value=release()), \
             patch.object(u, "_confirm", return_value=False), patch.object(u, "apply_release") as apply, redirect_stdout(io.StringIO()):
            u.command()
        apply.assert_not_called()
        self.assertFalse(self.target.root.exists())

    def test_readonly_json_check_no_installation_access(self):
        out = io.StringIO()
        with patch.object(u, "latest_release", return_value=release()), patch.object(u, "installation") as install, redirect_stdout(out):
            u.command(check_only=True, json_output=True)
        self.assertTrue(json.loads(out.getvalue())["update_available"])
        install.assert_not_called()

    def test_broken_runtime_rollback_stays_on_original_launcher(self):
        self.prepared()
        with patch.object(u, "installation", return_value=self.target), patch.object(sys, "argv", ["romeo-mcp", "serve"]):
            with self.assertRaisesRegex(u.UpdateError, "rollback"):
                u.dispatch()
        with patch.object(u, "installation", side_effect=AssertionError("dispatch unwanted")), \
             patch.object(sys, "argv", ["romeo-mcp", "update", "--rollback"]):
            u.dispatch()

    def test_notice_cached_stderr_only_and_optional(self):
        class InlineThread:
            def __init__(self, target, **kwargs):
                self.target = target
            def start(self):
                self.target()
        out, err = io.StringIO(), io.StringIO()
        with patch.object(u, "installation", return_value=self.target), patch.object(u.threading, "Thread", InlineThread), \
             patch.object(u, "latest_release", return_value=release()) as fetch, \
             patch.dict(os.environ, ROMEO_UPDATE_CHECK="1"), redirect_stdout(out), redirect_stderr(err):
            u.start_notice()
            u.start_notice()
            self.assertEqual(fetch.call_count, 1)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("9.0.0", err.getvalue())
        with patch.object(u.threading, "Thread") as thread:
            u.start_notice()
        thread.assert_not_called()


def dependency_wheel() -> bytes:
    """Une vraie dependance, installee par pip depuis un dossier local."""
    files = {
        "romeo_fixture_dep/__init__.py": 'VALUE = "installee"\n',
        "romeo_fixture_dep-1.0.0.dist-info/METADATA": "Metadata-Version: 2.1\nName: romeo-fixture-dep\nVersion: 1.0.0\n",
        "romeo_fixture_dep-1.0.0.dist-info/WHEEL": "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    }
    record = "romeo_fixture_dep-1.0.0.dist-info/RECORD"
    files[record] = "".join(f"{name},,\n" for name in [*files, record])
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return output.getvalue()


def fixture_lock(digest=None) -> str:
    digest = digest or hashlib.sha256(dependency_wheel()).hexdigest()
    return f"romeo-fixture-dep==1.0.0 \\\n    --hash=sha256:{digest}\n"


def fixture_wheel(locks=None) -> bytes:
    """Une vraie wheel minuscule, dont le verrou ne vise qu'une dependance locale."""
    files = {
        "romeo_mcp/__init__.py": '__version__ = "9.0.0"\n',
        **(locks or {"romeo_mcp/locks/server.lock": fixture_lock()}),
        "romeo_mcp/server.py": "server = object()\n",
        "romeo_mcp/__main__.py": """import json, os, sys
from . import __version__
if '--fixture-error' in sys.argv:
    sys.exit(23)
if '--fixture-echo' in sys.argv:
    print(json.dumps({'pid': os.getpid(), 'version': __version__}), flush=True)
    for line in sys.stdin:
        print(__version__ + ':' + line.strip(), flush=True)
else:
    print(__version__)
""",
        "romeo_mcp/documentation/page.md": "Documentation",
        "romeo_mcp/documentation/manifest.json": json.dumps({"files": {"page.md": hashlib.sha256(b"Documentation").hexdigest()}}),
        "romeo_mcp-9.0.0.dist-info/METADATA": "Metadata-Version: 2.1\nName: romeo-mcp\nVersion: 9.0.0\n",
        "romeo_mcp-9.0.0.dist-info/WHEEL": "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    }
    record = "romeo_mcp-9.0.0.dist-info/RECORD"
    files[record] = "".join(f"{name},,\n" for name in [*files, record])
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return output.getvalue()


class ProcessIntegrationTests(TemporaryInstallation):
    @unittest.skipUnless(os.name == "nt", "Job Object propre a Windows")
    def test_explicit_worker_breakaway_survives_launcher_exit(self):
        # Le lanceur garde ses serveurs dans un Job Object, mais un worker de
        # mise a jour doit pouvoir finir apres fermeture de ce lanceur.
        marker = self.root / "worker-finished.txt"
        started = self.root / "worker-started.txt"
        child_code = ("from pathlib import Path; import time; "
                      "Path(" + repr(str(started)) + ").write_text('started'); "
                      "time.sleep(0.8); Path(" + repr(str(marker)) + ").write_text('finished')")
        server_code = ("import subprocess, sys; "
                       "subprocess.Popen([sys.executable, '-I', '-c', " + repr(child_code) + "], "
                       "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, "
                       "creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_BREAKAWAY_FROM_JOB)")
        launcher_code = ("import sys, os; sys.path.insert(0, " + repr(str(ROOT)) + "); "
                         "from romeo_mcp.updates import _windows_run; "
                         "sys.exit(_windows_run([sys.executable, '-I', '-c', " + repr(server_code) + "], dict(os.environ)))")
        process = subprocess.run([sys.executable, "-I", "-c", launcher_code], capture_output=True, timeout=20)
        self.assertEqual(process.returncode, 0, process.stderr)
        import time
        deadline = time.monotonic() + 10
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertTrue(started.exists())
        self.assertTrue(marker.exists(), "le worker a ete arrete avec le lanceur")

    def test_real_install_dispatch_stdio_and_rollback_without_network(self):
        # Les chemins du lanceur restent constants meme apres un exec isole.
        env = {**os.environ, u.ORIGIN_ENV: json.dumps(self.target.origin),
               "ROMEO_UPDATES_DIR": str(self.root / "managed"), "PYTHONPATH": str(ROOT),
               "ROMEO_UPDATE_CHECK": "0", "PYTHONIOENCODING": "utf-8"}
        with patch.dict(os.environ, env):
            target = u.installation()
        data = fixture_wheel()
        expected = release(data)
        wheelhouse = self.root / "wheelhouse"
        wheelhouse.mkdir()
        (wheelhouse / "romeo_fixture_dep-1.0.0-py3-none-any.whl").write_bytes(dependency_wheel())
        private = self.root / "private-config.json"
        private.write_text('{"ROMEO_ACCOUNT":"test-project"}', encoding="utf-8")
        private_before = private.read_bytes()
        source_before = u._fingerprint(self.package)
        # Exercer le vrai worker detache avec une wheel locale, sans index.
        from romeo_mcp import update_service as service
        original_spawn = subprocess.Popen
        children = []
        encoded = base64.b64encode(data).decode("ascii")
        def offline_spawn(command, **kwargs):
            code = ("import sys; sys.path.insert(0, " + repr(str(ROOT)) + "); "
                    "import base64, io; from romeo_mcp import updates as u; "
                    "u._request = lambda url: io.BytesIO(base64.b64decode(" + repr(encoded) + ")); "
                    "u.verify_attestation = lambda *args, **kwargs: {'ok': True}; "
                    "original_run = u._run; "
                    "u._run = lambda command, **kwargs: original_run([*command, '--no-index', '--find-links', " + repr(str(wheelhouse)) + "] if 'pip' in command else command, **kwargs); "
                    "from romeo_mcp.update_worker import main; main()")
            child = original_spawn([command[0], "-I", "-c", code, command[-1]], **kwargs)
            children.append(child)
            return child
        with patch.dict(os.environ, env), patch.object(u, "latest_release", return_value=expected), \
             patch.object(service.subprocess, "Popen", side_effect=offline_spawn):
            launched = service.start(True, "9.0.0", target=target)
        self.assertTrue(launched["started"])
        self.assertFalse(launched["result_validated"])
        try:
            self.assertEqual(children[0].wait(timeout=60), 0, service.status(target=target))
        finally:
            if children[0].poll() is None:
                children[0].kill()
                children[0].wait(timeout=15)
        result = service.status(launched["operation_id"], target=target)["operation"]
        self.assertEqual(result["state"], "ready")
        self.assertTrue(result["result_validated"])
        self.assertEqual(result["version"], "9.0.0")
        installed = subprocess.run([str(target.executable(result["active"])), "-I", "-c",
                                    "import romeo_fixture_dep as dep; print(dep.VALUE)"],
                                   capture_output=True, text=True, timeout=30)
        self.assertEqual(installed.stdout.strip(), "installee", installed.stderr)
        self.assertEqual(u._fingerprint(self.package), source_before)
        self.assertEqual(private.read_bytes(), private_before)
        launcher = [sys.executable, "-m", "romeo_mcp"]
        version = subprocess.run([*launcher, "--version"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(version.returncode, 0, version.stderr)
        self.assertEqual(version.stdout.strip(), "9.0.0")
        failed = subprocess.run([*launcher, "--fixture-error"], cwd=ROOT, env=env, capture_output=True, timeout=30)
        self.assertEqual(failed.returncode, 23, failed.stderr)
        with subprocess.Popen([*launcher, "--fixture-echo"], cwd=ROOT, env=env,
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as process:
            try:
                # communicate(timeout) ne convient pas ici : garder stdin ouvert
                # pendant le retour arriere pour verifier un serveur deja actif.
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as reader:
                    future = reader.submit(process.stdout.readline)
                    try:
                        greeting = future.result(timeout=30)
                    except BaseException:
                        process.kill()
                        raise
                self.assertEqual(json.loads(greeting)["version"], "9.0.0")
                self.assertIsNone(process.poll(), "le lanceur doit vivre autant que le serveur")
                outcome = u.rollback(target, target.state())
                self.assertEqual(outcome["version"], "1.0.0")
                self.assertIsNone(target.state()["active"])
                output, error = process.communicate("ping\n", timeout=30)
                self.assertEqual(output.strip(), "9.0.0:ping")
                self.assertEqual(process.returncode, 0, error)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=15)
        self.assertTrue(target.slot_dir(result["active"]).exists())
        self.assertEqual(private.read_bytes(), private_before)
        # Revenir de nouveau sur l'environnement conserve est possible.
        self.assertEqual(u.rollback(target, target.state())["version"], "9.0.0")

    def test_real_pip_installs_exact_hash_and_refuses_any_other(self):
        environment = self.root / "venv"
        subprocess.run([sys.executable, "-I", "-m", "venv", str(environment)], check=True, timeout=120)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        wheelhouse = self.root / "wheelhouse"
        wheelhouse.mkdir()
        (wheelhouse / "romeo_fixture_dep-1.0.0-py3-none-any.whl").write_bytes(dependency_wheel())
        local_index = ["--no-index", "--find-links", str(wheelhouse)]
        original = u._run
        offline = lambda command, **kwargs: original([*command, *local_index], **kwargs)
        wrong, right = self.root / "wrong.lock", self.root / "right.lock"
        wrong.write_text(fixture_lock("0" * 64), encoding="utf-8")
        right.write_text(fixture_lock(), encoding="utf-8")
        probe = [str(python), "-I", "-c", "import romeo_fixture_dep"]
        with patch.object(u, "_run", side_effect=offline):
            with self.assertRaisesRegex(u.UpdateError, "(?i)hash"):
                u.install_locked(python, wrong)
            self.assertNotEqual(subprocess.run(probe, capture_output=True, timeout=30).returncode, 0)
            u.install_locked(python, right)
        self.assertEqual(subprocess.run(probe, capture_output=True, timeout=30).returncode, 0)

    def test_lock_is_read_from_the_wheel_and_required(self):
        with_lock, without = self.root / "with.whl", self.root / "without.whl"
        with_lock.write_bytes(fixture_wheel())
        self.assertEqual(u.extract_wheel_lock(with_lock, self.root / "lock").read_text(encoding="utf-8"), fixture_lock())
        with zipfile.ZipFile(without, "w") as archive:
            archive.writestr("romeo_mcp/__init__.py", "")
        for path in (without, self.root / "absente.whl"):
            with self.assertRaisesRegex(u.UpdateError, "sans verrou"):
                u.extract_wheel_lock(path, self.root / "lock-2")

    def test_attestation_identity_binds_repository_workflow_and_tag(self):
        calls = []
        def checker(command, **kwargs):
            calls.append(command)
            digest, identity = command[command.index("--digest") + 1], command[command.index("--identity") + 1]
            return json.dumps({"ok": True, "sha256": digest, "identity": identity})
        with patch.object(u, "attestation_bundles", return_value=[b"{}"]), \
             patch.object(u, "verifier_python", return_value=Path("python")), patch.object(u, "_run", side_effect=checker):
            self.target.root.mkdir(parents=True)
            result = u.verify_attestation(self.target, "a" * 64, "refs/tags/v9.0.0")
        self.assertEqual(result["identity"], f"https://github.com/{u.REPOSITORY}/.github/workflows/ci.yml@refs/tags/v9.0.0")
        self.assertIn("-I", calls[0])
        lying = lambda command, **kwargs: json.dumps({"ok": True, "sha256": "b" * 64, "identity": "autre"})
        for answer in (lying, lambda command, **kwargs: "pas du json",
                       lambda command, **kwargs: json.dumps({"ok": False, "error": "refus"})):
            with patch.object(u, "attestation_bundles", return_value=[b"{}"]), \
                 patch.object(u, "verifier_python", return_value=Path("python")), patch.object(u, "_run", side_effect=answer):
                with self.assertRaises(u.UpdateError):
                    u.verify_attestation(self.target, "a" * 64, "refs/tags/v9.0.0")

    def test_missing_or_unavailable_attestations_refuse_installation(self):
        for error, needle in ((HTTPError(u.API, 404, "missing", {}, None), "Aucune attestation"),
                              (HTTPError(u.API, 403, "limit", {}, None), "HTTP 403"),
                              (URLError("offline"), "injoignables")):
            with patch.object(u, "_request", side_effect=error), self.assertRaisesRegex(u.UpdateError, needle):
                u.attestation_bundles("a" * 64)
        for body in (b"{}", b"pas du json", b'{"attestations": []}', b'{"attestations": "x"}', b'{"attestations": [{}]}'):
            with patch.object(u, "_request", return_value=io.BytesIO(body)), self.assertRaises(u.UpdateError):
                u.attestation_bundles("a" * 64)

    def test_attestation_storage_is_only_allowed_for_bundles(self):
        class Response(io.BytesIO):
            def geturl(self):
                return "https://tmaproduction.blob.core.windows.net/attestations/1.json"
        with patch.object(u, "urlopen", side_effect=lambda *args, **kwargs: Response(b"")):
            with self.assertRaisesRegex(u.UpdateError, "Redirection"):
                u._request(u.API)
            self.assertEqual(u._request(u.API, attestation_storage=True).read(), b"")

    def test_snappy_decoder_handles_literals_copies_and_corruption(self):
        from romeo_mcp.attestation_check import decode_snappy
        # "abcd" litteral puis copie de 8 octets a l'offset 4 (format bloc Snappy).
        self.assertEqual(decode_snappy(bytes([12, 3 << 2]) + b"abcd" + bytes([(8 - 1) << 2 | 2, 4, 0])), b"abcdabcdabcd")
        self.assertEqual(decode_snappy(bytes([5, 4 << 2]) + b"hello"), b"hello")
        for corrupted in (b"", bytes([5, 4 << 2]) + b"he", bytes([12, 3 << 2]) + b"abcd" + bytes([(8 - 1) << 2 | 2, 9, 0]),
                          bytes([4, 3 << 2]) + b"abcd" + bytes([(8 - 1) << 2 | 2, 4, 0]), b"\xff\xff\xff\xff\xff\xff"):
            with self.assertRaises((ValueError, IndexError)):
                decode_snappy(corrupted)

    def test_repository_locks_pin_every_requirement_by_hash(self):
        from tools.prepare_release import REQUIRED_LOCKS, lock_problem
        for name, package in REQUIRED_LOCKS.items():
            self.assertIsNone(lock_problem((ROOT / name).read_text(encoding="utf-8"), package), name)
        self.assertEqual(lock_problem("mcp==2.0.0\n", "mcp"), "exigence sans version figee ou sans empreinte")
        self.assertEqual(lock_problem("mcp>=2 --hash=sha256:aa\n", "mcp"), "mcp absent du verrou")

    def test_release_preparation_rejects_version_mismatch_and_selects_assets(self):
        from tools.prepare_release import prepare
        (self.root / "romeo_mcp").mkdir()
        (self.root / "romeo_mcp/__init__.py").write_text('__version__ = "9.0.0"\n', encoding="utf-8")
        metadata = b'[project]\nversion = "9.0.0"\n'
        (self.root / "pyproject.toml").write_bytes(metadata)
        (self.root / "CHANGELOG.md").write_text("# Versions\n\n## 9.0.0\n\nNotes neuves.\n\n## 8.0.0\nAnciennes notes.\n", encoding="utf-8")
        dist = self.root / "dist"
        dist.mkdir()
        wheel = dist / "romeo_mcp-9.0.0-py3-none-any.whl"
        wheel.write_bytes(fixture_wheel({"romeo_mcp/locks/server.lock": "mcp==2.3.0 \\\n    --hash=sha256:" + "a" * 64 + "\n",
                                         "romeo_mcp/locks/verifier.lock": "sigstore==4.5.1 \\\n    --hash=sha256:" + "b" * 64 + "\n"}))
        with tarfile.open(dist / "romeo_mcp-9.0.0.tar.gz", "w:gz") as archive:
            info = tarfile.TarInfo("romeo_mcp-9.0.0/pyproject.toml")
            info.size = len(metadata)
            archive.addfile(info, io.BytesIO(metadata))
        (dist / "unrelated.whl").write_bytes(b"do not publish")
        outputs = prepare("v9.0.0", self.root)
        self.assertEqual(len(outputs), 3)
        self.assertNotIn("unrelated", (dist / "SHA256SUMS").read_text())
        self.assertEqual((dist / "release-notes.md").read_text().strip(), "Notes neuves.")
        self.assertIn(hashlib.sha256(wheel.read_bytes()).hexdigest(), (dist / "SHA256SUMS").read_text())
        with self.assertRaisesRegex(ValueError, "correspondre"):
            prepare("v9.0.1", self.root)
        wheel.write_bytes(fixture_wheel({"romeo_mcp/locks/server.lock": "mcp==2.3.0 --hash=sha256:aa\n"}))
        with self.assertRaises(KeyError):
            prepare("v9.0.0", self.root)
        wheel.write_bytes(fixture_wheel())
        with self.assertRaisesRegex(ValueError, "mcp absent"):
            prepare("v9.0.0", self.root)
        wheel.write_bytes(fixture_wheel({"romeo_mcp/locks/server.lock": "mcp==2.3.0\n",
                                         "romeo_mcp/locks/verifier.lock": "sigstore==4.5.1 --hash=sha256:bb\n"}))
        with self.assertRaisesRegex(ValueError, "empreinte"):
            prepare("v9.0.0", self.root)


if __name__ == "__main__":
    unittest.main(verbosity=2)
