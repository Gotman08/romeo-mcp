"""Bounded, numeric-only rsync observations for detached transfers.

The progress2 percentage is rsync's aggregate observation. Its rounded value
does not establish an exact total, nor does 100 percent establish copy integrity.
"""
from __future__ import annotations

import math
import os
from pathlib import Path
import re
import subprocess
import time

MAX_TAIL = 16384
_LINE = re.compile(
    rb"\s*([0-9]{1,16})\s+([0-9]{1,3})%\s+([0-9]{1,12}(?:\.[0-9]{1,2})?)([kMG])B/s"
    rb"\s+([0-9]{1,4}:[0-9]{2}:[0-9]{2}|\?\?:\?\?:\?\?)"
    rb"(\s+\(xfr#[0-9]+, to-chk=[0-9]+/[0-9]+\))?\s*\Z"
)


def parse(line: bytes, observed_at: float) -> dict | None:
    """Accept only complete, C-locale progress2 records; never export log text."""
    match = _LINE.fullmatch(line)
    if match is None:
        return None
    done, percent = int(match[1]), int(match[2])
    speed = float(match[3]) * {b"k": 1024, b"M": 1024 ** 2, b"G": 1024 ** 3}[match[4]]
    if done > 2 ** 53 or percent > 100 or not math.isfinite(speed):
        return None
    eta = None
    # A record with xfr#/to-chk reports elapsed time, not time remaining.
    if match[6] is None and b"?" not in match[5]:
        hours, minutes, seconds = map(int, match[5].split(b":"))
        if minutes > 59 or seconds > 59:
            return None
        eta = hours * 3600 + minutes * 60 + seconds
    return {"source": "rsync_progress2", "bytes_transferred": done, "bytes_total": None,
            "percent_reported": percent, "bytes_per_second": speed,
            "eta_seconds": eta, "observed_at": observed_at}


def command(argv: list[str], environment: dict) -> tuple[list[str], bool]:
    """Add local aggregate statistics only when the installed rsync supports it."""
    if Path(argv[0]).name.lower() not in {"rsync", "rsync.exe"}:
        return argv, False
    try:
        version = subprocess.run([argv[0], "--version"], stdin=subprocess.DEVNULL,
                                 capture_output=True, timeout=2, env=environment,
                                 **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}))
        match = re.search(rb"rsync\s+version\s+([0-9]+)\.([0-9]+)", version.stdout[:4096])
        if version.returncode or not match or tuple(map(int, match.groups())) < (3, 1):
            return argv, False
    except (OSError, subprocess.TimeoutExpired):
        return argv, False
    return [argv[0], "--info=progress2", "--no-inc-recursive", "--no-human-readable", *argv[1:]], True


class ProgressLog:
    """Read new complete records with bounded memory, retaining the evidence age."""
    def __init__(self, path: Path):
        self.path = path
        self.offset = path.stat().st_size if path.exists() else 0
        self.pending = b""
        self.discarding = False

    def sample(self) -> dict | None:
        try:
            with self.path.open("rb") as stream:
                size = stream.seek(0, 2)
                if size < self.offset:
                    self.offset, self.pending = 0, b""
                    self.discarding = False
                begin = max(self.offset, size - MAX_TAIL)
                stream.seek(begin)
                data = stream.read(MAX_TAIL)
                if begin > self.offset:
                    self.pending = b""
                    self.discarding = True
                self.offset = stream.tell()
        except OSError:
            return None
        parts = re.split(rb"[\r\n]", self.pending + data)
        self.pending = parts.pop()
        if self.discarding and parts:
            parts.pop(0)
            self.discarding = False
        if len(self.pending) > 512:
            self.pending, self.discarding = b"", True
        latest = None
        for item in parts:
            if len(item) > 512:
                continue
            observed = parse(item, time.time())
            if observed is not None:
                latest = observed
        return latest
