"""Cooperative resource reservations across threads and processes.

SQLite serializes only reservation bookkeeping. A kernel lock witnesses each
live owner, so a crashed process cannot leave a permanent reservation. The
standalone portion is also sent to ROMEO; no package installation is needed.
"""

# BEGIN STANDALONE
import contextlib
import json
import os
import re
import sqlite3
import stat
import uuid
from contextvars import ContextVar
from pathlib import Path

_OWNED_LEASES = ContextVar('romeo_owned_resource_leases', default=())
_LEASE_NAME = re.compile(r'[a-f0-9]{32}\.lock')


class ResourceBusy(ValueError):
    """The operation has not acquired its resources and must not execute."""


def _kernel_lock(descriptor):
    if os.name == 'nt':
        import msvcrt
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _lease_open(path, create=False):
    flags = os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    if create:
        flags |= os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('Verrou de ressource non regulier ou lie.')
        if hasattr(os, 'getuid') and info.st_uid != os.getuid():
            raise ValueError('Verrou de ressource d\'un autre utilisateur.')
        if create:
            os.write(descriptor, b'0')
        _kernel_lock(descriptor)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _resources(entries):
    normalized = {}
    for value, write in entries:
        value = str(value)
        if not value or type(write) is not bool:
            raise ValueError('Reservation de ressource invalide.')
        if value.startswith('action:'):
            key, kind, identity = value, 'action', None
        else:
            key, kind = os.path.normcase(os.path.realpath(os.path.abspath(value))), 'path'
            try:
                info = os.stat(key)
                identity = [info.st_dev, info.st_ino] if info.st_ino else None
            except FileNotFoundError:
                identity = None
        prior = normalized.get((kind, key))
        normalized[kind, key] = {'kind': kind, 'key': key, 'write': write or bool(prior and prior['write']),
                                 'identity': identity}
    if not 1 <= len(normalized) <= 64:
        raise ValueError('Une reservation doit contenir entre 1 et 64 ressources.')
    return list(normalized.values())


def _overlap(left, right):
    if not (left['write'] or right['write']) or left['kind'] != right['kind']:
        return False
    if left['key'] == right['key']:
        return True
    if left['kind'] == 'action':
        return False
    if left['identity'] is not None and left['identity'] == right['identity']:
        return True
    a, b = left['key'].rstrip(os.sep) + os.sep, right['key'].rstrip(os.sep) + os.sep
    return a.startswith(b) or b.startswith(a)


class ResourceLease:
    def __init__(self, entries, root=None):
        self.entries = entries
        self.root = Path(root or os.environ.get('ROMEO_CONCURRENCY_ROOT')
                         or Path.home() / '.romeo-mcp' / 'concurrency').expanduser().resolve()
        self.identifier = uuid.uuid4().hex
        self.descriptor = None
        self.context_token = None

    @contextlib.contextmanager
    def _transaction(self):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        database = self.root / 'resources.db'
        if database.is_symlink():
            raise ValueError('Le registre de concurrence ne doit pas etre un lien.')
        connection = sqlite3.connect(database, timeout=3, isolation_level=None)
        try:
            os.chmod(database, 0o600)
            connection.execute('CREATE TABLE IF NOT EXISTS leases (id TEXT PRIMARY KEY, resources TEXT NOT NULL)')
            connection.execute('BEGIN IMMEDIATE')
            yield connection
            connection.commit()
        except sqlite3.OperationalError as exc:
            connection.rollback()
            raise ResourceBusy('Registre de concurrence occupe ; operation non demarree.') from exc
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _reap(self, connection):
        live = []
        rows = connection.execute('SELECT id, resources FROM leases').fetchall()
        if len(rows) > 128:
            raise ResourceBusy('Trop de reservations de ressources actives.')
        recorded = {row[0] for row in rows}
        candidates = list(self.root.iterdir())
        if len(candidates) > 1024:
            raise ResourceBusy('Registre de concurrence trop volumineux.')
        for path in candidates:
            if not _LEASE_NAME.fullmatch(path.name):
                continue
            try:
                descriptor = _lease_open(path)
            except FileNotFoundError:
                continue
            except OSError:
                if path.stem in recorded:
                    live.append(path.stem)
                continue
            os.close(descriptor)
            path.unlink()
            connection.execute('DELETE FROM leases WHERE id=?', (path.stem,))
        for identifier, resources in rows:
            if identifier not in live:
                connection.execute('DELETE FROM leases WHERE id=?', (identifier,))
        return [(identifier, json.loads(resources)) for identifier, resources in rows if identifier in live]

    def __enter__(self):
        requested = _resources(self.entries)
        owned = _OWNED_LEASES.get()
        try:
            with self._transaction() as connection:
                live = self._reap(connection)
                if len(live) >= 128:
                    raise ResourceBusy('Trop de reservations de ressources actives.')
                for identifier, reserved in live:
                    if (str(self.root), identifier) not in owned and any(
                            _overlap(left, right) for left in requested for right in reserved):
                        raise ResourceBusy('Conflit de concurrence : une autre operation utilise cette ressource. '
                                           'Relis son resultat avant de reessayer.')
                self.descriptor = _lease_open(self.root / (self.identifier + '.lock'), create=True)
                connection.execute('INSERT INTO leases VALUES (?,?)',
                                   (self.identifier, json.dumps(requested)))
        except BaseException:
            self._close()
            raise
        self.context_token = _OWNED_LEASES.set((*owned, (str(self.root), self.identifier)))
        return self

    def _close(self):
        if self.descriptor is not None:
            os.close(self.descriptor)
            self.descriptor = None
            try:
                (self.root / (self.identifier + '.lock')).unlink(missing_ok=True)
            except OSError:
                # A closed owner is stale even when antivirus/share modes
                # briefly prevent unlink. The next reservation reaps it.
                pass

    def __exit__(self, *exc):
        try:
            try:
                with self._transaction() as connection:
                    connection.execute('DELETE FROM leases WHERE id=?', (self.identifier,))
                    self._close()
            except (OSError, ValueError, sqlite3.Error):
                # Bookkeeping failure after execution must not misreport a
                # completed mutation as never started. Kernel ownership ends
                # below; stale index rows can be safely recovered next time.
                pass
        finally:
            self._close()
            if self.context_token is not None:
                _OWNED_LEASES.reset(self.context_token)
                self.context_token = None

# END STANDALONE


def remote_source():
    """Freeze exactly the shared implementation when a remote helper is built."""
    source = Path(__file__).read_text(encoding='utf-8')
    return source.split('# BEGIN STANDALONE\n', 1)[1].split('# END STANDALONE', 1)[0]
