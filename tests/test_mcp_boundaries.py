"""Regressions des cinq defauts reproduits sans soumission de job."""
from __future__ import annotations

import json
import base64
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import offline
from romeo_mcp import guard, outils_contexte as context, outils_donnees as data
from romeo_mcp import outils_execution as execution
from romeo_mcp.observability import ReadCache
from romeo_mcp.ssh import RomeoSession, Result, clamp

BASH = shutil.which("bash")
if os.name == "nt" and Path(r"C:\Program Files\Git\bin\bash.exe").is_file():
    BASH = r"C:\Program Files\Git\bin\bash.exe"


@unittest.skipUnless(BASH, "bash local necessaire, aucun acces SSH")
class FramingTests(unittest.TestCase):
    def setUp(self):
        self.connection = RomeoSession("offline-host")
        popen = subprocess.Popen
        self.local_popen = popen
        self.enterContext(patch("romeo_mcp.ssh.subprocess.Popen", side_effect=lambda argv, **kw:
                                popen([BASH, "--noprofile", "--norc"], **kw)))
        self.addCleanup(self.connection.close)

    def test_exact_text_without_lf_and_with_trailing_lf(self):
        for text in ("", "no_newline", "ligne\n", "ligne\n\n\n", "ligne\r\n", "été 😀\r"):
            with self.subTest(text=repr(text)):
                # Le bash Git de Windows retire les CR litteraux de son entree.
                # Produire les octets par printf teste le flux, pas ce comportement.
                octal = "".join("\\0" + format(byte, "03o") for byte in text.encode("utf-8"))
                result = self.connection.run("printf '%b' " + shlex.quote(octal), timeout=1)
                self.assertEqual(result.rc, 0)
                self.assertEqual(result.stdout, text)

    def test_no_lf_preserves_nonzero_exit_and_stderr(self):
        result = self.connection.run("printf no_lf >&2; exit 42", timeout=1)
        self.assertEqual((result.rc, result.stdout), (42, "no_lf"))
        self.assertEqual(self.connection.run("printf next", timeout=1).stdout, "next")

    def test_startup_banner_without_lf_does_not_hide_begin_marker(self):
        with patch("romeo_mcp.ssh.subprocess.Popen", side_effect=lambda argv, **kw:
                   self.local_popen([BASH, "--noprofile", "--norc", "-c",
                             "printf banner_no_lf; exec bash --noprofile --norc"], **kw)):
            result = self.connection.run("printf actual", timeout=2)
        self.assertEqual(result.stdout, "actual")

    def test_marker_prefix_in_content_is_not_a_footer(self):
        token = SimpleNamespace(hex="a" * 32)
        text = "__ROMEO_E_" + token.hex + "__ not-a-status\n"
        with patch("romeo_mcp.ssh.uuid.uuid4", return_value=token):
            result = self.connection.run("printf '%s' " + shlex.quote(text), timeout=1)
        self.assertEqual(result.stdout, text)

    def test_long_single_line_is_captured_and_bounded(self):
        result = self.connection.run("printf '%01048576d' 0", timeout=5, max_chars=512)
        self.assertTrue(result.truncated)
        self.assertLess(len(result.stdout), 700)
        self.assertEqual(self.connection.run("printf alive", timeout=1).stdout, "alive")


class SpackBudgetTests(unittest.TestCase):
    def setUp(self):
        self.connection = SimpleNamespace(host="offline-host", user="test-user")
        self.enterContext(patch.object(context, "session", return_value=self.connection))
        self.enterContext(patch.object(context, "_SPACK_CACHE", ReadCache(8)))

    def test_multimegabyte_catalog_preserves_details_and_cached_search(self):
        values = [{"name": "package" + str(i), "version": "1.2", "hash": format(i + 1, "032x"),
                   "parameters": {"padding": "x" * 1200}, "dependencies": []} for i in range(1500)]
        text = json.dumps(values)
        self.assertGreater(len(text), 1_800_000)
        def remote(*args, **kw):
            output, truncated = clamp(text, kw["max_chars"])
            return Result(0, output, 0, truncated)
        with patch.object(context, "_sh", side_effect=remote) as call:
            observed = context.romeo_software(arch="x64cpu", limit=200)
            self.assertTrue(observed["ok"], observed)
            self.assertEqual(observed["total_in_catalog"], 1500)
            self.assertEqual(len(observed["specifications"]), 200)
            self.assertEqual(observed["specifications"][0]["load_spec"], "/" + values[0]["hash"])
            self.assertTrue(context.romeo_software(arch="x64cpu", search="package1")["observation"]["cached"])
            self.assertEqual(call.call_count, 1)
            self.assertFalse(context.romeo_software(arch="armgpu")["observation"]["cached"])
            self.assertEqual(call.call_count, 2)

    def test_incomplete_or_failed_catalog_is_never_cached(self):
        for result in (Result(0, "[{", 0), Result(0, "[]", 0, True), Result(1, "loader failed", 0)):
            with self.subTest(result=result), patch.object(context, "_sh", return_value=result) as call:
                self.assertFalse(context.romeo_software()["ok"])
                self.assertFalse(context.romeo_software()["ok"])
                self.assertEqual(call.call_count, 2)

    def test_catalog_above_explicit_budget_is_refused_without_caching(self):
        text = json.dumps([{"name": "large", "version": "1", "hash": "a" * 32,
                            "parameters": {"padding": "x" * (8 * 1024 * 1024 + 1)}}])
        def remote(*args, **kw):
            output, truncated = clamp(text, kw["max_chars"])
            return Result(0, output, 0, truncated)
        with patch.object(context, "_sh", side_effect=remote) as call:
            self.assertFalse(context.romeo_software()["ok"])
            self.assertFalse(context.romeo_software()["ok"])
            self.assertEqual(call.call_count, 2)


class LoginGuardTests(unittest.TestCase):
    def test_wrapped_heavy_commands_and_nested_shells_are_rejected(self):
        wrappers = ("env ", "env -i X=1 ", "command ", "command -p ", "timeout 1 ",
                    "nice -n 2 ", "nohup ", "exec ", "sudo -n ", "stdbuf -oL ")
        for prefix in wrappers:
            for command in ("make -j8", "python train.py", "python3 -m pip install numpy"):
                with self.subTest(command=prefix + command), self.assertRaises(guard.GuardError):
                    guard.check_login_command(prefix + command)
        for command in ("bash -c 'make -j8'", "bash -lc 'env make'", "sh -c 'command python train.py'",
                        'echo "$(make)"', "eval 'make'", "source train.sh", "X=make; $X -j8",
                        "python train.py -c pass", "python -m torch -- -c", "python -W ignore train.py"):
            with self.subTest(command=command), self.assertRaises(guard.GuardError):
                guard.check_login_command(command)

    def test_recursive_root_deletions_remain_rejected_with_allow_heavy(self):
        for command in ("rm -rf -- /", "rm --recursive --force /", "rm -rf / # commentaire",
                        "env rm -rf -- /", "bash -c 'rm --recursive /'", "rm / -fr", "rm -r //",
                        "rm -rf /./", 'rm -rf "$HOME"', "rm -rf ~/", "dd if=/dev/zero of=/dev/sda"):
            for allow in (False, True):
                with self.subTest(command=command, allow=allow), self.assertRaises(guard.GuardError):
                    guard.check_login_command(command, allow_heavy=allow)

    def test_legitimate_inspection_and_literal_arguments_remain_allowed(self):
        for command in ("ls -la", "git status", "cat x | head -20", "OMP_NUM_THREADS=4 echo test",
                        "python -c 'print(1)'", "python3 --version", "squeue -u $USER",
                        "command -v make", "env python --version", "nice -n 2 git status",
                        "timeout 1 ls", "bash -c 'pwd'", "srun --pty bash",
                        "echo 'rm -rf /; make'", "printf '%s' ';'", "echo '# make'", "echo literal#hash"):
            with self.subTest(command=command):
                guard.check_login_command(command)
        guard.check_login_command("env python3 -m pip install numpy", allow_heavy=True)

    def test_refusal_precedes_remote_execution(self):
        with patch.object(execution, "session"), patch.object(execution, "_sh", return_value=Result(0, "", 0)) as remote:
            result = execution.login_command_run("env make -j8")
        self.assertFalse(result["ok"])
        self.assertTrue(result["refused"])
        remote.assert_not_called()


class FileBudgetTests(unittest.TestCase):
    def test_invalid_character_budget_is_refused_before_ssh(self):
        fake = SimpleNamespace(home="/home/test", scratch="/scratch/test", path_aliases=[])
        for value in (-1, 0, 64_001, 2**63, True, 1.5, "100", None):
            with self.subTest(value=value), patch.object(data, "session", return_value=fake), \
                    patch.object(data, "_sh", return_value=Result(0, "x\n", 0)) as remote:
                self.assertFalse(data.read_remote_file("text.txt", max_chars=value)["ok"])
                remote.assert_not_called()


@unittest.skipUnless(BASH, "bash local necessaire, aucun acces SSH")
class DirectoryAndReadTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="romeo-boundaries-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.remote_root = self.root.as_posix()
        if os.name == "nt":
            self.remote_root = "/" + self.remote_root[0].lower() + self.remote_root[2:]
        fake = SimpleNamespace(home=self.remote_root, scratch=self.remote_root, path_aliases=[])
        self.enterContext(patch.object(data, "session", return_value=fake))
        self.enterContext(patch.object(data, "_sh", side_effect=self.local_command))

    def local_command(self, connection, command, **kw):
        words = shlex.split(command)
        if words[0] == "python3":
            argv = [sys.executable, *words[1:]]
            if os.name == "nt":
                argv[3] = str(self.root / Path(argv[3]).relative_to(self.remote_root))
        else:
            argv = [BASH, "--noprofile", "--norc", "-c", command]
        result = subprocess.run(argv, capture_output=True, encoding="utf-8", timeout=10)
        text, truncated = clamp(result.stdout + result.stderr, kw.get("max_chars", 12000))
        return Result(result.returncode, text, 0, truncated)

    @unittest.skipIf(os.name == "nt", "Windows interdit LF et tabulation dans les noms locaux")
    def test_newlines_tabs_quotes_unicode_and_symlink_names(self):
        names = ["line\nbreak.txt", "tab\tname", "apostrophe'", "été 😀", "space name"]
        for name in names:
            (self.root / name).write_text("content", encoding="utf-8")
        (self.root / "link").symlink_to("missing target")
        observed = data.list_dir(self.remote_root)
        self.assertTrue(observed["ok"], observed)
        entries = {entry["name"]: entry for entry in observed["entries"]}
        self.assertEqual(set(entries), {*names, "link"})
        self.assertTrue(entries["link"]["is_symlink"])
        self.assertFalse(entries["link"]["is_dir"])

    @unittest.skipIf(os.name == "nt", "Noms POSIX en octets invalides UTF-8")
    def test_non_utf8_filename_preserves_bytes_without_invalid_mcp_text(self):
        raw_name = b"bad-\xff"
        with open(os.fsencode(self.root) + b"/" + raw_name, "wb"):
            pass
        observed = data.list_dir(self.remote_root)
        self.assertTrue(observed["ok"], observed)
        entry = observed["entries"][0]
        self.assertEqual(entry["name"], "bad-�")
        self.assertEqual(base64.b64decode(entry["name_bytes_base64"]), raw_name)
        entry["name"].encode("utf-8")

    def test_list_limit_empty_and_missing(self):
        self.assertEqual(data.list_dir(self.remote_root)["count"], 0)
        for i in range(5):
            (self.root / str(i)).touch()
        result = data.list_dir(self.remote_root, limit=2)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["count"], 2)
        self.assertTrue(result["truncated"])
        self.assertFalse(data.list_dir(self.remote_root + "/missing")["ok"])

    def test_read_unicode_pagination_and_exact_budget(self):
        text = "première 😀\n" + "é😀" * 100_000 + "\nlast_no_lf"
        (self.root / "text").write_text(text, encoding="utf-8", newline="")
        first = data.read_remote_file(self.remote_root + "/text", limit=1)
        self.assertEqual(first["content"], "première 😀\n")
        self.assertEqual(first["total_lines"], "3")
        second = data.read_remote_file(self.remote_root + "/text", offset=2, limit=1, max_chars=73)
        self.assertTrue(second["truncated"])
        self.assertEqual(second["content"], ("é😀" * 100_000)[:73])
        last = data.read_remote_file(self.remote_root + "/text", offset=3, max_chars=64_000)
        self.assertEqual(last["content"], "last_no_lf")
        self.assertFalse(last["truncated"])


if __name__ == "__main__":
    unittest.main()
