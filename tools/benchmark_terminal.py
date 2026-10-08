"""Measure the local reader on synthetic data; optionally measure a Linux PTY.

No SSH, GitHub, user configuration or user registry is accessed. Baselines run
in separate processes so importing two package versions cannot mix their code.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import statistics
import sqlite3
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def fixture(root, jobs, transfers):
    sys.path.insert(0, str(ROOT))
    from romeo_mcp.registry import _SCHEMA
    at = time.time()
    path = root / "jobs.db"
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript(_SCHEMA)
        for number in range(1, jobs + 1):
            state = "RUNNING" if number == 1 else "COMPLETED"
            connection.execute("INSERT INTO jobs(job_id,name,partition,submitted_at,last_state) VALUES(?,?,?,?,?)",
                               (str(number), "Synthetic job " + str(number), "cpu", at - jobs + number, state))
            payload = {"job_id": str(number), "ok": True, "state": state, "result_validated": number != 1}
            connection.execute("INSERT INTO job_observations VALUES(?,?,?,?)", (str(number), "{}", at - 1, json.dumps(payload)))
        connection.commit()
    for number in range(transfers):
        identifier = f"{number:032x}"
        directory = root / "transfers" / identifier
        directory.mkdir(parents=True)
        plan = {"id": identifier, "direction": "download", "local_path": f"synthetic-{number}.bin",
                "remote_path": f"synthetic/{number}.bin", "recursive": False, "verify": True,
                "target": {}, "created_at": at}
        plan["sha256"] = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
        (directory / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        (directory / "status.json").write_text(json.dumps({"transfer_id": identifier, "state": "completed",
            "heartbeat_at": at - 1, "ok": True, "result_validated": True}), encoding="utf-8")
    return path


def environment(root):
    return {**os.environ, "ROMEO_CONFIG": str(root / "config.json"), "ROMEO_MCP_DB": str(root / "jobs.db"),
            "ROMEO_UPDATES_DIR": str(root / "updates"), "ROMEO_REPORTS_DIR": str(root / "reports"),
            "ROMEO_UPDATE_CHECK": "0", "ROMEO_AUTO_ISSUES": "0", "PYTHONIOENCODING": "utf-8"}


def worker(options):
    sys.path.insert(0, str(options.package))
    from romeo_mcp import terminal_data
    reader = None
    if options.mode == "catalog":
        from romeo_mcp.terminal_catalog import Catalog
        reader = Catalog(db=options.db)
        collect = reader.snapshot
    else:
        collect = lambda: terminal_data.snapshot(db=options.db)
    samples, cpu_samples = [], []
    try:
        for _ in range(options.repeats + 1):
            start, cpu = time.perf_counter(), time.process_time()
            result = collect()
            samples.append((time.perf_counter() - start) * 1000)
            cpu_samples.append((time.process_time() - cpu) * 1000)
        coverage = result.get("coverage", {})
        output = {"cold_ms": samples[0], "warm_median_ms": statistics.median(samples[1:]),
                  "warm_cpu_median_ms": statistics.median(cpu_samples[1:]),
                  "page_jobs": len(result["jobs"]), "page_transfers": len(result["transfers"]),
                  "known_jobs": coverage.get("jobs", {}).get("total", len(result["jobs"])),
                  "known_transfers": coverage.get("transfers", {}).get("total", len(result["transfers"])),
                  "old_active_loaded": any(row["id"] == "1" for row in result["jobs"])}
        if reader is not None:
            output.update(job_reads=reader.job_reads, transfer_json_reads=reader.files.reads,
                          transfer_directory_scans=reader.files.scans)
        if sys.platform.startswith("linux"):
            import resource
            output["peak_reader_rss_mib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        print(json.dumps(output))
    finally:
        if reader is not None:
            reader.close()


def idle(binary, package, root):
    """Sum CPU of the owned UI and its reader over 6 s, including one 5 s poll."""
    import fcntl
    import pty
    import select
    import struct
    import termios
    master, slave = pty.openpty()
    process = None
    try:
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 100, 0, 0))
        original = termios.tcgetattr(slave)
        process = subprocess.Popen([str(binary), "--python", sys.executable, "--package-root", str(package),
                                    "--db", str(root / "jobs.db"), "--color", "always"],
            stdin=slave, stdout=slave, stderr=slave, env={**environment(root), "HOME": str(root), "TERM": "xterm-256color"},
            start_new_session=True)
        def drain(seconds):
            until = time.monotonic() + seconds
            while time.monotonic() < until:
                if process.poll() is not None:
                    raise RuntimeError("The synthetic native session stopped")
                if select.select([master], [], [], 0.05)[0]:
                    os.read(master, 65536)
        drain(2)
        readers = [int(value) for value in Path(f"/proc/{process.pid}/task/{process.pid}/children").read_text().split()]
        if not readers:
            raise RuntimeError("Private reader missing")
        owned = [process.pid, *readers]
        def sample():
            ticks, rss = 0, 0
            for pid in owned:
                stat = Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()
                ticks += int(stat[11]) + int(stat[12])
                for line in Path(f"/proc/{pid}/status").read_text().splitlines():
                    if line.startswith("VmRSS:"):
                        rss += int(line.split()[1])
            return ticks / os.sysconf("SC_CLK_TCK"), rss / 1024
        before = sample()
        start = time.monotonic()
        drain(6)
        after = sample()
        elapsed = time.monotonic() - start
        os.write(master, b"q")
        if process.wait(timeout=10) != 0 or termios.tcgetattr(slave) != original:
            raise RuntimeError("Terminal cleanup failed")
        if any(Path(f"/proc/{pid}").exists() for pid in readers):
            raise RuntimeError("Private reader survived")
        return {"seconds": elapsed, "cpu_percent_one_core": (after[0] - before[0]) * 100 / elapsed,
                "rss_sum_mib": after[1], "refresh_seconds": 5, "terminal_restored": True}
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        os.close(master)
        os.close(slave)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--jobs", type=int, default=1000)
    parser.add_argument("--transfers", type=int, default=200)
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--baseline-binary", type=Path)
    parser.add_argument("--mode", choices=["catalog", "legacy"], help=argparse.SUPPRESS)
    parser.add_argument("--package", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--db", type=Path, help=argparse.SUPPRESS)
    options = parser.parse_args()
    if not 1 <= options.jobs <= 10000 or not 0 <= options.transfers <= 10000 or not 3 <= options.repeats <= 100:
        parser.error("Use 1..10000 jobs, 0..10000 transfers and 3..100 repeats")
    if options.mode:
        worker(options)
        return
    if (options.binary or options.baseline_binary) and not sys.platform.startswith("linux"):
        parser.error("PTY idle measurements currently require Linux")
    with tempfile.TemporaryDirectory(prefix="romeo-benchmark-") as directory:
        root = Path(directory)
        path = fixture(root, options.jobs, options.transfers)
        result = {"synthetic": True, "jobs": options.jobs, "transfers": options.transfers,
                  "repeats": options.repeats, "platform": sys.platform, "python": sys.version.split()[0]}
        for label, package, mode in (("current", ROOT, "catalog"), ("baseline", options.baseline, "legacy")):
            if package is not None:
                output = subprocess.check_output([sys.executable, str(Path(__file__).resolve()), "--mode", mode,
                    "--package", str(package.resolve()), "--db", str(path), "--repeats", str(options.repeats)],
                    env=environment(root), text=True, encoding="utf-8", timeout=120)
                result[label] = json.loads(output)
        for label, binary, package in (("current_idle", options.binary, ROOT),
                                      ("baseline_idle", options.baseline_binary, options.baseline)):
            if binary is not None and package is not None:
                result[label] = idle(binary.resolve(), package.resolve(), root)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
