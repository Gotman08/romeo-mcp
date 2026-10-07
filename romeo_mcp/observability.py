"""Bounded, process-local read caches and aggregate timings; no payload logging."""
from __future__ import annotations

import copy
import threading
import time
from collections import OrderedDict
from contextlib import contextmanager


class ReadCache:
    """Only explicitly selected reads enter this cache; failures are never stored."""

    def __init__(self, capacity=64, clock=time.monotonic):
        self.capacity = capacity
        self.clock = clock
        self._lock = threading.RLock()
        self._entries = OrderedDict()
        self.hits = self.misses = 0

    def get(self, key, max_age):
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and max_age > 0:
                age = max(0.0, self.clock() - entry[0])
                if age <= max_age:
                    self._entries.move_to_end(key)
                    self.hits += 1
                    return copy.deepcopy(entry[1]), age
                self._entries.pop(key)
            self.misses += 1
        return None

    def put(self, key, value):
        with self._lock:
            self._entries[key] = (self.clock(), copy.deepcopy(value))
            self._entries.move_to_end(key)
            while len(self._entries) > self.capacity:
                self._entries.popitem(last=False)

    def clear(self):
        with self._lock:
            self._entries.clear()

    def snapshot(self):
        with self._lock:
            return {"entries": len(self._entries), "capacity": self.capacity,
                    "hits": self.hits, "misses": self.misses}


class Measurements:
    """Aggregate durations by fixed operation name, without arguments or output."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.started = clock()
        self._lock = threading.Lock()
        self._rows = {}

    def record(self, name, elapsed, failed=False):
        with self._lock:
            row = self._rows.setdefault(name, {"count": 0, "failures": 0, "total_seconds": 0.0,
                                               "max_seconds": 0.0, "last_seconds": 0.0})
            row["count"] += 1
            row["failures"] += bool(failed)
            row["total_seconds"] += elapsed
            row["max_seconds"] = max(row["max_seconds"], elapsed)
            row["last_seconds"] = elapsed

    @contextmanager
    def measure(self, name):
        start = self.clock()
        failed = False
        try:
            yield
        except BaseException:
            failed = True
            raise
        finally:
            self.record(name, self.clock() - start, failed)

    def snapshot(self):
        with self._lock:
            rows = copy.deepcopy(self._rows)
        for row in rows.values():
            row["mean_seconds"] = row["total_seconds"] / row["count"]
        return {"scope": "current_process", "uptime_seconds": self.clock() - self.started,
                "operations": rows, "payloads_recorded": False}


READS = ReadCache(capacity=16)
TIMINGS = Measurements()
