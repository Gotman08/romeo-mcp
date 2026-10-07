"""Real Linux PTY smoke test: navigation, recovery, timeouts and terminal cleanup.

Uses synthetic data only. The regular Python suites do not require this binary.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import select
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def session(binary: Path, exit_key: bytes) -> dict:
    import fcntl
    import pty
    import struct
    import termios

    master, slave = pty.openpty()
    process = None
    reader_ids: list[int] = []
    output = bytearray()
    try:
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 100, 0, 0))
        before = termios.tcgetattr(slave)
        process = subprocess.Popen([str(binary), "--python", sys.executable, "--package-root", str(ROOT),
                                    "--demo", "--refresh", "1"], stdin=slave, stdout=slave, stderr=slave,
                                   env={**os.environ, "TERM": "xterm-256color"}, start_new_session=True)
        screen_height = 30

        def expect(value: str, timeout: float = 10) -> None:
            nonlocal screen_height
            deadline = time.monotonic() + timeout
            redraw_at = time.monotonic() + 0.5
            def trace() -> str:
                # Crossterm replaces runs of spaces with cursor-right escapes
                # and splits text with style changes; those are not data bytes.
                decoded = output.decode("utf-8", "replace")
                decoded = re.sub(r"\x1b\[(\d+)C", lambda match: " " * min(200, int(match[1])), decoded)
                return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", decoded)

            # Differential frames can preserve a space already on screen.
            # Compare the new text without spaces rather than treating cursor
            # positioning as an ordinary stream of printable characters.
            expected = "".join(value.split())
            while expected not in "".join(trace().split()):
                if process.poll() is not None:
                    raise AssertionError(f"Interface arrêtée avant l'affichage : {value}")
                if time.monotonic() >= deadline:
                    raise AssertionError(f"Affichage attendu absent : {value}")
                if time.monotonic() >= redraw_at:
                    # A differential frame can update isolated characters at
                    # arbitrary positions. Resize to request a complete frame
                    # rather than claim a screen state from concatenated diffs.
                    output.clear()
                    screen_height = 31 if screen_height == 30 else 30
                    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", screen_height, 100, 0, 0))
                    os.kill(process.pid, signal.SIGWINCH)
                    redraw_at = time.monotonic() + 0.5
                if select.select([master], [], [], 0.1)[0]:
                    output.extend(os.read(master, 65536))

        expect("DÉMONSTRATION")
        expect("Simulation à reprendre")
        children = Path(f"/proc/{process.pid}/task/{process.pid}/children")
        if children.is_file():
            reader_ids = [int(value) for value in children.read_text().split()]
        if not reader_ids:
            raise AssertionError("Aucun lecteur Python détenu par l'interface")
        os.write(master, b"2")
        expect("Jobs")
        expect("Simulation MPI")
        os.write(master, b"/x\r")
        expect("Aucun job ne correspond")
        os.write(master, b"p")
        expect("pause")
        os.write(master, b"?")
        expect("Aide")
        recovered = False
        timeout_observed = False
        if exit_key == b"q":
            # Pause keeps recovery explicit; only processes created by this test
            # are stopped. Old data must remain usable throughout the failure.
            output.clear()
            os.write(master, b"\x1b")
            expect("Jobs 0/4")
            os.kill(reader_ids[0], signal.SIGTERM)
            os.write(master, b"r")
            expect("Lecture interrompue")
            os.write(master, b"r")
            deadline = time.monotonic() + 5
            replacement = []
            while time.monotonic() < deadline:
                replacement = [int(value) for value in children.read_text().split()
                               if int(value) not in reader_ids]
                if replacement:
                    break
                time.sleep(0.05)
            if not replacement or any(Path(f"/proc/{pid}").exists() for pid in reader_ids):
                raise AssertionError("Le lecteur interrompu n'a pas ete remplace et recolte")
            reader_ids.extend(replacement)
            # Ensure the replacement replied before testing a stopped reader.
            output.clear()
            os.write(master, b"!")
            expect("Aucune alerte de lecture enregistrée")
            output.clear()
            os.write(master, b"\x1b")
            expect("Jobs 0/4")
            recovered = True
            os.kill(replacement[0], signal.SIGSTOP)
            os.write(master, b"r")
            output.clear()
            expect("Lecture interrompue", timeout=14)
            os.write(master, b"!")
            expect("Le lecteur local ne répond pas (10 s)")
            if Path(f"/proc/{replacement[0]}").exists():
                raise AssertionError("Le lecteur bloque subsiste apres le delai")
            timeout_observed = True
        os.write(master, exit_key)
        code = process.wait(timeout=10)
        if code != 0:
            raise AssertionError(f"Code de sortie inattendu : {code}")
        if termios.tcgetattr(slave) != before:
            raise AssertionError("Le terminal n'a pas retrouvé ses attributs initiaux")
        if any(Path(f"/proc/{pid}").exists() for pid in reader_ids):
            raise AssertionError("Un lecteur Python subsiste après la fermeture")
        return {"exit": "q" if exit_key == b"q" else "Ctrl-C", "code": code,
                "terminal_restored": True, "reader_stopped": True, "navigation_verified": True,
                "reader_recovered": recovered, "reader_timeout_cleaned": timeout_observed}
    finally:
        for pid in reader_ids:
            try:
                status = Path(f"/proc/{pid}/status").read_text()
                if process is None or not re.search(rf"^PPid:\s+{process.pid}$", status, re.MULTILINE):
                    continue
                os.kill(pid, signal.SIGCONT)
                os.kill(pid, signal.SIGTERM)
            except (FileNotFoundError, ProcessLookupError):
                pass
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        os.close(master)
        os.close(slave)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--binary", type=Path, required=True)
    args = parser.parse_args()
    if not sys.platform.startswith("linux"):
        parser.error("Ce test de session utilise le PTY et /proc de Linux.")
    binary = args.binary.expanduser().resolve()
    if not binary.is_file():
        parser.error("Binaire compilé introuvable")
    print(json.dumps({"sessions": [session(binary, b"q"), session(binary, b"\x03")]}))


if __name__ == "__main__":
    main()
