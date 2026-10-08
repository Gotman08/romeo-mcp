"""Resource evidence from saved job records. Never evaluate a submitted script."""
from __future__ import annotations

import re

_DIRECTIVE = re.compile(r"^\s*#SBATCH\s+--([a-z-]+)(?:=|\s+)([0-9]+)\s*$")
_OMP = re.compile(r"^\s*(?:export\s+)?OMP_NUM_THREADS=['\"]?([0-9]+)['\"]?\s*$")
_FIELDS = {"nodes": "nodes", "ntasks": "tasks", "ntasks-per-node": "tasks_per_node",
           "cpus-per-task": "cpus_per_task", "gpus": "gpus", "gpus-per-node": "gpus_per_node",
           "gpus-per-task": "gpus_per_task"}


def count(value):
    """Only finite, explicit integer counts; a Slurm nodelist is not a count."""
    if isinstance(value, str) and re.fullmatch(r"[0-9]{1,9}", value):
        value = int(value)
    return value if type(value) is int and 0 <= value <= 1_000_000 else None


def resources(script, observation):
    requested = {}
    if isinstance(script, str):
        for line in script.splitlines():
            match = _DIRECTIVE.fullmatch(line)
            if match and match[1] in _FIELDS and count(match[2]) is not None:
                requested[_FIELDS[match[1]]] = count(match[2])
            omp = _OMP.fullmatch(line)
            if omp and count(omp[1]) is not None:
                requested["omp_threads"] = count(omp[1])
    observed = {}
    if isinstance(observation, dict):
        for source, destination in (("nodes", "nodes"), ("ntasks", "tasks"),
                                    ("ntasks_per_node", "tasks_per_node"),
                                    ("cpus_per_task", "cpus_per_task"), ("gpus", "gpus"),
                                    ("gpus_per_node", "gpus_per_node"),
                                    ("gpus_per_task", "gpus_per_task"), ("omp_threads", "omp_threads")):
            value = count(observation.get(source))
            if value is not None:
                observed[destination] = value
    return {"requested": requested, "observed": observed}
