"""Bounded, numeric-only copy observations for detached transfers.

The progress2 percentage is rsync's aggregate observation. Its rounded value
does not establish an exact total, nor does 100 percent establish copy integrity.
"""
from __future__ import annotations

import math
import os
from pathlib import Path
import re
import subprocess
import stat
import time

MAX_TAIL = 16384
MAX_BYTES = 2 ** 53
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


def regular_file_signature(path: Path, stable: bool = True) -> tuple | None:
    """Observe a regular local file without accepting links or reparse points.

    O_NOFOLLOW is unavailable on Windows. Comparing lstat before/after fstat
    also refuses a replaced entry there; no file content is read by the probe.
    """
    try:
        before = path.lstat()
    except FileNotFoundError:
        return None

    def identity(info):
        if (not stat.S_ISREG(info.st_mode) or info.st_ino <= 0
                or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise ValueError("La mesure locale refuse les liens et fichiers speciaux.")
        # Windows lstat/fstat expose different legacy creation/change ctimes.
        # Identity, size and mtime remain comparable; POSIX keeps change time.
        changed_at = info.st_ctime_ns if os.name != "nt" else None
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, changed_at

    initial = identity(before)
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    try:
        opened = identity(os.fstat(descriptor))
        after = identity(path.lstat())
        changed = (initial != opened or after != opened) if stable else (initial[:2] != opened[:2] or after[:2] != opened[:2])
        if changed:
            raise ValueError("Le fichier local a change pendant sa mesure.")
        return opened
    finally:
        os.close(descriptor)


class LocalDestination:
    """Measure only the private local payload; replacement invalidates it."""
    def __init__(self, path: Path):
        self.path = path
        self.identity = None
        self.invalid = False

    def sample(self) -> int | None:
        if self.invalid:
            return None
        try:
            current = regular_file_signature(self.path, stable=False)
            if current is None:
                if self.identity is not None:
                    raise ValueError("La copie locale a disparu.")
                return 0
            identity = current[:2]
            if self.identity is not None and identity != self.identity:
                raise ValueError("La copie locale a ete remplacee.")
            self.identity = identity
            return current[2]
        except (OSError, ValueError):
            self.invalid = True
            return None


class DestinationProgress:
    """Logical bytes present in a copy, never network bytes or integrity.

    An invalid observation is permanent for this copy. A repeated size remains
    a fresh observation; a heartbeat without a call to sample() does not.
    """
    def __init__(self, total: int, read_sample, read_final_sample=None):
        if type(total) is not int or not 0 < total <= MAX_BYTES:
            raise ValueError("La progression exige une taille totale fiable et positive.")
        self.total = total
        self.read_sample = read_sample
        self.read_final_sample = read_final_sample
        self.previous = None
        self.latest = None
        self.invalid = False

    def sample(self) -> dict | None:
        return self._sample(self.read_sample)

    def finish(self) -> dict | None:
        return self._sample(self.read_final_sample or self.read_sample)

    def _sample(self, read_sample) -> dict | None:
        if self.invalid:
            return None
        try:
            reading = read_sample()
            if reading is None:
                # Waiting for telemetry is not a new observation or a failure.
                return dict(self.latest) if self.latest is not None else None
            done = reading.get("bytes_present") if isinstance(reading, dict) else None
            if (not isinstance(reading, dict) or reading.get("valid") is not True
                    or type(done) is not int or not 0 <= done <= self.total
                    or type(reading.get("bytes_total")) is not int or reading["bytes_total"] != self.total):
                raise ValueError("La taille observee n'est plus fiable.")
            measured = reading['observed_monotonic'] if 'observed_monotonic' in reading else time.monotonic()
            observed_at = reading['observed_at'] if 'observed_at' in reading else time.time()
            if (type(measured) not in (int, float) or not math.isfinite(measured)
                    or type(observed_at) not in (int, float) or not math.isfinite(observed_at) or observed_at < 0):
                raise ValueError("Horodatage de mesure invalide.")
            if self.previous is not None and (done < self.previous[0] or measured < self.previous[1]):
                raise ValueError("La taille observee a regresse.")
            speed = eta = None
            if self.previous is not None and measured > self.previous[1]:
                speed = (done - self.previous[0]) / (measured - self.previous[1])
                if not math.isfinite(speed):
                    raise ValueError("Debit invalide.")
                if speed > 0:
                    eta = math.ceil((self.total - done) / speed)
            self.previous = done, measured
            self.latest = {"source": "scp_destination_size", "bytes_transferred": done, "bytes_total": self.total,
                    "percent_reported": done * 100 // self.total, "bytes_per_second": speed,
                    "eta_seconds": eta, "observed_at": observed_at}
            return dict(self.latest)
        except (OSError, ValueError, TypeError, KeyError):
            self.invalid = True
            self.latest = None
            return None
        except Exception:
            self.invalid = True
            self.latest = None
            raise
