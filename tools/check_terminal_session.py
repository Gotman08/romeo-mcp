"""Real Linux PTY smoke test: navigation, q/Ctrl-C, termios and reader cleanup.

Uses synthetic data only. The regular Python suites do not require this binary.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import select
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

        def expect(value: str) -> None:
            deadline = time.monotonic() + 10
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
                if select.select([master], [], [], 0.1)[0]:
                    output.extend(os.read(master, 65536))

        expect("DÉMONSTRATION")
        children = Path(f"/proc/{process.pid}/task/{process.pid}/children")
        if children.is_file():
            reader_ids = [int(value) for value in children.read_text().split()]
        if not reader_ids:
            raise AssertionError("Aucun lecteur Python détenu par l'interface")
        os.write(master, b"2")
        expect("Jobs ·")
        expect("Simulation MPI")
        os.write(master, b"/x\r")
        expect("Aucun job ne correspond")
        os.write(master, b"p")
        expect("pause")
        os.write(master, b"?")
        expect("Aide")
        os.write(master, exit_key)
        code = process.wait(timeout=10)
        if code != 0:
            raise AssertionError(f"Code de sortie inattendu : {code}")
        if termios.tcgetattr(slave) != before:
            raise AssertionError("Le terminal n'a pas retrouvé ses attributs initiaux")
        if any(Path(f"/proc/{pid}").exists() for pid in reader_ids):
            raise AssertionError("Un lecteur Python subsiste après la fermeture")
        return {"exit": "q" if exit_key == b"q" else "Ctrl-C", "code": code,
                "terminal_restored": True, "reader_stopped": True, "navigation_verified": True}
    finally:
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
