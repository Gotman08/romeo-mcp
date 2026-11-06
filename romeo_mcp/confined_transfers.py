"""Transferts SCP via des descripteurs distants conserves pendant la copie.

Un precontrole de realpath suivi de scp laisserait une course sur les liens.
Le superviseur conserve donc les descripteurs, fournit leur chemin /proc et
publie les envois depuis un dossier prive. Les repertoires recus sont copies
dans un instantane prive, sans suivre les liens de leur contenu.
"""
from __future__ import annotations

import json
import queue
import shlex
import subprocess
import threading

from .remote_paths import CONFINED_PATHS
from .resource_locks import remote_source
from .ssh import SSHError, _environnement_ssh


SUPERVISOR = CONFINED_PATHS + remote_source() + r'''
import hashlib, json, select, secrets, signal, stat, sys
request = json.loads(sys.argv[1])
roots = request['roots']
held = []
stage_parent = stage = stage_name = None
lease = None
response_kind, response_id = 'ready', None
progress_invalid = False
payload_identity = None
payload_size = 0
source_signature = None
total = request.get('bytes_total')
if type(total) is not int or not 0 < total <= 2**53:
    total = None

def keep(fd):
    held.append(fd)
    return fd

def signature(info):
    if not stat.S_ISREG(info.st_mode):
        raise ValueError('La mesure exige un fichier regulier.')
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns

def sample_progress():
    global progress_invalid, payload_identity, payload_size
    if progress_invalid or is_dir or total is None:
        return {'valid': False, 'bytes_present': None, 'bytes_total': total}
    try:
        if request['direction'] == 'download':
            if signature(os.fstat(source)) != source_signature:
                raise ValueError('La source distante a change.')
            return {'valid': True, 'bytes_present': None, 'bytes_total': total}
        try:
            payload = os.open('payload', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=stage)
        except FileNotFoundError:
            if payload_identity is not None:
                raise ValueError('La copie distante a disparu.')
            return {'valid': True, 'bytes_present': 0, 'bytes_total': total}
        try:
            current = signature(os.fstat(payload))
            bound = signature(os.stat('payload', dir_fd=stage, follow_symlinks=False))
            identity, done = current[:2], current[2]
            if (identity != bound[:2] or payload_identity is not None and identity != payload_identity
                    or not payload_size <= done <= total):
                raise ValueError('La copie distante a change pendant sa mesure.')
            payload_identity, payload_size = identity, done
            return {'valid': True, 'bytes_present': done, 'bytes_total': total}
        finally:
            os.close(payload)
    except (OSError, ValueError):
        progress_invalid = True
        return {'valid': False, 'bytes_present': None, 'bytes_total': total}

def interrupted(*args):
    raise RuntimeError('Transfert interrompu.')

signal.signal(signal.SIGTERM, interrupted)
signal.signal(signal.SIGHUP, interrupted)

def active():
    if select.select([sys.stdin], [], [], 0)[0]:
        raise RuntimeError('Transfert interrompu avant publication.')

def digest(fd):
    value = hashlib.sha256()
    os.lseek(fd, 0, os.SEEK_SET)
    while True:
        active()
        block = os.read(fd, 1048576)
        if not block:
            break
        value.update(block)
    os.lseek(fd, 0, os.SEEK_SET)
    return value.hexdigest()

def info_at(fd, name):
    try:
        return os.stat(name, dir_fd=fd, follow_symlinks=False)
    except FileNotFoundError:
        return None

def ordinary(info):
    if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
        raise ValueError('Un transfert de repertoire refuse les liens symboliques et fichiers speciaux.')

def scan(fd):
    with os.scandir(fd) as entries:
        return [entry.name for entry in entries]

def validate_tree(fd):
    for name in scan(fd):
        active()
        info = os.stat(name, dir_fd=fd, follow_symlinks=False)
        ordinary(info)
        if stat.S_ISDIR(info.st_mode):
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            try:
                validate_tree(child)
            finally:
                os.close(child)

def copy_tree(source, destination):
    for name in scan(source):
        active()
        child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=source)
        try:
            info = os.fstat(child)
            ordinary(info)
            if stat.S_ISDIR(info.st_mode):
                os.mkdir(name, 0o700, dir_fd=destination)
                target = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=destination)
                try:
                    copy_tree(child, target)
                finally:
                    os.close(target)
            else:
                target = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=destination)
                try:
                    while True:
                        active()
                        block = os.read(child, 1048576)
                        if not block:
                            break
                        view = memoryview(block)
                        while view:
                            view = view[os.write(target, view):]
                finally:
                    os.close(target)
        finally:
            os.close(child)

def publish(source, destination):
    for name in scan(source):
        current = os.stat(name, dir_fd=source, follow_symlinks=False)
        ordinary(current)
        previous = info_at(destination, name)
        if previous is not None:
            ordinary(previous)
        if stat.S_ISDIR(current.st_mode) and previous is not None and stat.S_ISDIR(previous.st_mode):
            source_child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=source)
            try:
                target_child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=destination)
                try:
                    publish(source_child, target_child)
                finally:
                    os.close(target_child)
            finally:
                os.close(source_child)
        else:
            os.replace(name, name, src_dir_fd=source, dst_dir_fd=destination)

def remove_tree(fd):
    for name in scan(fd):
        info = os.stat(name, dir_fd=fd, follow_symlinks=False)
        if stat.S_ISDIR(info.st_mode):
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            try:
                remove_tree(child)
            finally:
                os.close(child)
            os.rmdir(name, dir_fd=fd)
        else:
            os.unlink(name, dir_fd=fd)

def staging(parent):
    global stage_parent, stage, stage_name
    stage_parent = parent
    stage_name = '.romeo-transfer-' + secrets.token_hex(16)
    os.mkdir(stage_name, 0o700, dir_fd=parent)
    stage = keep(os.open(stage_name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent))
    return '/proc/{}/fd/{}'.format(os.getpid(), stage)

try:
    path = request['path']
    if request['direction'] == 'upload':
        is_dir = request['recursive']
        # SCP met la source dans une destination existante de type repertoire.
        try:
            probe = confined_open(path, roots, os.O_RDONLY | os.O_NONBLOCK)
        except FileNotFoundError:
            probe = None
        if probe is not None and stat.S_ISDIR(os.fstat(probe).st_mode):
            parent = keep(probe)
            name = request['basename']
            actual = os.path.join(path, name)
        else:
            if probe is not None:
                os.close(probe)
            parent, name = confined_parent(path, roots)
            keep(parent)
            actual = path
        previous = info_at(parent, name)
        physical = os.path.join(os.readlink('/proc/self/fd/{}'.format(parent)), name)
        lease = ResourceLease([(physical, True)], request.get('lock_root') or
                              os.path.join(roots[0], '.romeo-mcp', 'concurrency'))
        lease.__enter__()
        if previous is not None:
            ordinary(previous)
        proxy = staging(parent) + '/payload'
        checksum = None
    else:
        lease = ResourceLease([(path, False)], request.get('lock_root') or
                              os.path.join(roots[0], '.romeo-mcp', 'concurrency'))
        lease.__enter__()
        source = keep(confined_open(path, roots, os.O_RDONLY | os.O_NONBLOCK))
        info = os.fstat(source)
        ordinary(info)
        is_dir = stat.S_ISDIR(info.st_mode)
        if stat.S_ISDIR(info.st_mode):
            if not request['recursive']:
                raise ValueError('recursive=true requis pour un repertoire.')
            temporary = keep(confined_open('/tmp', roots, os.O_RDONLY | os.O_DIRECTORY))
            proxy = staging(temporary)
            name = request['basename']
            os.mkdir(name, 0o700, dir_fd=stage)
            snapshot = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=stage)
            try:
                copy_tree(source, snapshot)
            finally:
                os.close(snapshot)
            proxy += '/' + name
            checksum = None
        else:
            proxy = '/proc/{}/fd/{}'.format(os.getpid(), source)
            source_signature = signature(info)
            total = info.st_size if 0 < info.st_size <= 2**53 else None
            checksum = digest(source) if request['verify'] else None
        actual = path
    if is_dir:
        total = None
    print(json.dumps({'ok': True, 'kind': 'ready', 'proxy': proxy, 'actual_path': actual,
                      'is_dir': is_dir, 'bytes_total': total}), flush=True)
    while True:
        action = json.loads(sys.stdin.readline() or '{}')
        response_kind = action.get('action') if isinstance(action, dict) else 'error'
        response_id = action.get('request_id') if isinstance(action, dict) else None
        if response_kind not in ('sample', 'commit') or type(response_id) is not int or response_id < 1:
            raise RuntimeError('Transfert annule ou protocole de supervision invalide.')
        if response_kind == 'commit':
            break
        print(json.dumps({'ok': True, 'kind': 'sample', 'request_id': response_id, **sample_progress()}), flush=True)
    if request['direction'] == 'upload':
        payload = os.open('payload', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=stage)
        try:
            current = os.fstat(payload)
            ordinary(current)
            if stat.S_ISDIR(current.st_mode):
                validate_tree(payload)
            elif request['verify']:
                checksum = digest(payload)
                if action.get('expected_sha256') is not None and checksum != action['expected_sha256']:
                    raise ValueError('Source locale modifiee ou copie corrompue ; publication refusee.')
            previous = info_at(parent, name)
            if previous is not None:
                ordinary(previous)
            if stat.S_ISDIR(current.st_mode) and previous is not None and stat.S_ISDIR(previous.st_mode):
                destination = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                try:
                    publish(payload, destination)
                finally:
                    os.close(destination)
            else:
                os.replace('payload', name, src_dir_fd=stage, dst_dir_fd=parent)
        finally:
            os.close(payload)
    elif checksum is not None and checksum != digest(source):
        raise ValueError('Le fichier distant a change pendant le transfert.')
    print(json.dumps({'ok': True, 'kind': 'commit', 'request_id': response_id,
                      'sha256': checksum, 'actual_path': actual}), flush=True)
except Exception as exc:
    print(json.dumps({'ok': False, 'kind': response_kind, 'request_id': response_id, 'error': str(exc)[:500]}), flush=True)
finally:
    if stage is not None:
        remove_tree(stage)
        os.rmdir(stage_name, dir_fd=stage_parent)
    for fd in reversed(held):
        os.close(fd)
    if lease is not None and lease.descriptor is not None:
        lease.__exit__(None, None, None)
'''


class TransferGuard:
    def __init__(self, host, path, roots, direction, basename, recursive=False, verify=True, bytes_total=None):
        self.host = host
        self.request = dict(path=path, roots=roots, direction=direction, basename=basename,
                            recursive=recursive, verify=verify, bytes_total=bytes_total)
        self.process = None
        self.messages = queue.Queue()
        self.ready = None
        self.result = None
        self.exchange_lock = threading.Lock()
        self.request_id = 0
        self.pending_sample = None
        self.sample_times = {}
        self.broken = False

    def _decode(self, line, kind, request_id=None):
        if line is None:
            raise SSHError('Supervision distante du transfert : canal ferme avant la reponse.')
        try:
            data = json.loads(line)
        except (ValueError, TypeError) as exc:
            raise SSHError('Supervision distante du transfert : reponse invalide.') from exc
        if not isinstance(data, dict) or type(data.get('ok')) is not bool:
            raise SSHError('Supervision distante du transfert : reponse invalide.')
        if (data.get('kind') != kind
                or request_id is not None and (type(data.get('request_id')) is not int or data['request_id'] != request_id)):
            raise SSHError('Supervision distante du transfert : reponse non correlee.')
        if data.get('ok') is not True:
            error = data.get('error')
            raise SSHError(error[:500] if isinstance(error, str) else 'Transfert distant refuse.')
        if kind == 'sample':
            issued = self.sample_times.pop(request_id, None)
            if issued is None:
                raise SSHError('Supervision distante du transfert : reponse non correlee.')
            # Local request time is a conservative bound on evidence age.
            # Never accept timing fields supplied by the remote response.
            data['observed_at'], data['observed_monotonic'] = issued
        return data

    def _receive(self, kind='ready', request_id=None, timeout=None):
        import time
        from .files import _TRANSFER_TIMEOUT, _CANCEL_CHECK
        deadline = time.monotonic() + (_TRANSFER_TIMEOUT if timeout is None else timeout)
        while True:
            checker = _CANCEL_CHECK.get()
            if checker is not None:
                checker()
            try:
                line = self.messages.get(timeout=min(.25, max(0, deadline-time.monotonic())))
                return self._decode(line, kind, request_id)
            except queue.Empty as exc:
                if time.monotonic() >= deadline:
                    raise SSHError('Supervision distante du transfert : delai de reponse depasse.') from exc

    def _send(self, action, **fields):
        """Send a small request while holding exchange_lock."""
        import time
        from .files import _CANCEL_CHECK
        checker = _CANCEL_CHECK.get()
        if checker is not None:
            checker()
        if self.broken or self.result is not None:
            raise SSHError('Canal de supervision du transfert indisponible.')
        self.request_id += 1
        if action == 'sample':
            self.sample_times[self.request_id] = time.time(), time.monotonic()
        self.process.stdin.write(json.dumps({'action': action, 'request_id': self.request_id, **fields}) + '\n')
        self.process.stdin.flush()
        return self.request_id

    def _drain_sample(self, timeout=None):
        if self.pending_sample is not None:
            self._receive('sample', self.pending_sample, timeout)
            self.pending_sample = None

    def _exchange(self, action, timeout=None, **fields):
        import time
        from .files import _CANCEL_CHECK, _TRANSFER_TIMEOUT
        deadline = time.monotonic() + (_TRANSFER_TIMEOUT if timeout is None else timeout)
        while not self.exchange_lock.acquire(timeout=.25):
            checker = _CANCEL_CHECK.get()
            if checker is not None:
                checker()
            if time.monotonic() >= deadline:
                raise SSHError('Supervision distante du transfert : delai de reponse depasse.')
        try:
            try:
                checker = _CANCEL_CHECK.get()
                if checker is not None:
                    checker()
                if self.broken or self.result is not None:
                    raise SSHError('Canal de supervision du transfert indisponible.')
                # A sample can still be in flight after local invalidation.
                # Drain it before any final sample or publication request.
                self._drain_sample(max(0, deadline-time.monotonic()))
                request_id = self._send(action, **fields)
                data = self._receive(action, request_id, max(0, deadline-time.monotonic()))
                if action == 'commit':
                    self.result = data
                return data
            except BaseException:
                self.broken = True
                raise
        finally:
            self.exchange_lock.release()

    def __enter__(self):
        command = 'python3 -u -c {} {}'.format(shlex.quote(SUPERVISOR), shlex.quote(json.dumps(self.request)))
        options = {'creationflags': subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, 'CREATE_NO_WINDOW') else {}
        self.process = subprocess.Popen(
            ['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=30', self.host, command],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding='utf-8', env=_environnement_ssh(), **options)
        def receive():
            for line in self.process.stdout:
                self.messages.put(line)
            self.messages.put(None)
        self.reader = threading.Thread(target=receive, daemon=True)
        self.reader.start()
        try:
            self.ready = self._receive()
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def commit(self, expected_sha256=None):
        self.result = self._exchange('commit', expected_sha256=expected_sha256)
        return self.result

    def sample(self):
        """Poll one observation without delaying SCP or queuing more requests."""
        from .files import _CANCEL_CHECK
        if not self.exchange_lock.acquire(blocking=False):
            return None
        try:
            try:
                checker = _CANCEL_CHECK.get()
                if checker is not None:
                    checker()
                if self.broken or self.result is not None:
                    raise SSHError('Canal de supervision du transfert indisponible.')
                if self.pending_sample is None:
                    self.pending_sample = self._send('sample')
                try:
                    line = self.messages.get_nowait()
                except queue.Empty:
                    return None
                data = self._decode(line, 'sample', self.pending_sample)
                self.pending_sample = None
                return data
            except BaseException:
                self.broken = True
                raise
        finally:
            self.exchange_lock.release()

    def finish_sample(self):
        """After copy exit, drain old telemetry and request a fresh observation."""
        return self._exchange('sample')

    def __exit__(self, *args):
        if self.process is None:
            return
        if self.process.stdin:
            try:
                self.process.stdin.close()
            except OSError:
                pass
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=5)
        self.reader.join(timeout=1)
        self.process.stdout.close()
        if not args[0] and self.process.returncode:
            raise SSHError('Superviseur distant interrompu : publication ou nettoyage non confirme.')
