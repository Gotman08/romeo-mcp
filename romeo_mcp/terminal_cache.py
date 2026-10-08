"""Private reader cache. File identities invalidate parsed JSON, including WAL."""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path


def signature(path: Path):
    try:
        value = path.stat()
        return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    except FileNotFoundError:
        return None


def database_signature(path: Path):
    return (signature(path), signature(Path(str(path) + "-wal")), signature(Path(str(path) + "-journal")))


class JsonFiles:
    """Bounded parsed-file cache; callers must treat returned dictionaries as immutable."""
    def __init__(self, maximum=2048, byte_limit=8 * 1024 * 1024):
        self.maximum = maximum
        self.byte_limit = byte_limit
        self.bytes = 0
        self.files = OrderedDict()
        self.inventories = {}
        self.reads = 0
        self.scans = 0

    def clear(self):
        self.files.clear()
        self.inventories.clear()
        self.bytes = 0

    def read(self, path):
        from .terminal_data import read_json
        if path.is_symlink():
            raise ValueError("Une trace locale ne doit pas être un lien symbolique")
        stamp = signature(path)
        previous = self.files.get(path)
        if previous is not None and previous[0] == stamp:
            self.files.move_to_end(path)
            return previous[1]
        result = read_json(path)
        self.reads += 1
        # A concurrent atomic replacement is retried at the next request.
        if signature(path) == stamp:
            # Charge the original serialized size as well as bounding entries.
            # Oversized files are parsed for this read but never retained.
            previous = self.files.pop(path, None)
            if previous is not None:
                self.bytes -= previous[2]
            size = stamp[2] if stamp is not None else 0
            if size <= self.byte_limit:
                self.files[path] = (stamp, result, size)
                self.bytes += size
            while len(self.files) > self.maximum or self.bytes > self.byte_limit:
                self.bytes -= self.files.popitem(last=False)[1][2]
        return result

    def directories(self, root, *, files=False):
        import os
        from .terminal_data import IDENTIFIER
        stamp = signature(root)
        inventory_key = (root, files)
        previous = self.inventories.get(inventory_key)
        if previous is not None and previous[0] == stamp:
            return previous[1]
        if stamp is None:
            return ()
        with os.scandir(root) as entries:
            paths = tuple(Path(entry.path) for entry in entries
                          if (entry.is_file(follow_symlinks=False) if files else
                              IDENTIFIER.fullmatch(entry.name) and entry.is_dir(follow_symlinks=False)))
        self.scans += 1
        if signature(root) == stamp:
            self.inventories[inventory_key] = (stamp, paths)
        return paths
