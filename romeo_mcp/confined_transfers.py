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
from .ssh import SSHError, _environnement_ssh


SUPERVISOR = CONFINED_PATHS + r'''
import hashlib, json, select, secrets, signal, stat, sys
request = json.loads(sys.argv[1])
roots = request['roots']
held = []
stage_parent = stage = stage_name = None

def keep(fd):
    held.append(fd)
    return fd

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
        if previous is not None:
            ordinary(previous)
        proxy = staging(parent) + '/payload'
        checksum = None
    else:
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
            checksum = digest(source) if request['verify'] else None
        actual = path
    print(json.dumps({'ok': True, 'proxy': proxy, 'actual_path': actual, 'is_dir': is_dir}), flush=True)
    action = json.loads(sys.stdin.readline() or '{}')
    if action.get('action') != 'commit':
        raise RuntimeError('Transfert annule sans publication.')
    if request['direction'] == 'upload':
        payload = os.open('payload', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=stage)
        try:
            current = os.fstat(payload)
            ordinary(current)
            if stat.S_ISDIR(current.st_mode):
                validate_tree(payload)
            elif request['verify']:
                checksum = digest(payload)
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
    print(json.dumps({'ok': True, 'sha256': checksum, 'actual_path': actual}), flush=True)
except Exception as exc:
    print(json.dumps({'ok': False, 'error': str(exc)[:500]}), flush=True)
finally:
    if stage is not None:
        remove_tree(stage)
        os.rmdir(stage_name, dir_fd=stage_parent)
    for fd in reversed(held):
        os.close(fd)
'''


class TransferGuard:
    def __init__(self, host, path, roots, direction, basename, recursive=False, verify=True):
        self.host = host
        self.request = dict(path=path, roots=roots, direction=direction, basename=basename,
                            recursive=recursive, verify=verify)
        self.process = None
        self.messages = queue.Queue()
        self.ready = None
        self.result = None

    def _receive(self):
        import time
        from .files import _TRANSFER_TIMEOUT, _CANCEL_CHECK
        deadline = time.monotonic() + _TRANSFER_TIMEOUT
        try:
            while True:
                checker = _CANCEL_CHECK.get()
                if checker is not None:
                    checker()
                try:
                    line = self.messages.get(timeout=min(.25, max(0, deadline-time.monotonic())))
                    break
                except queue.Empty:
                    if time.monotonic() >= deadline:
                        raise
            data = json.loads(line)
        except (queue.Empty, ValueError, TypeError) as exc:
            raise SSHError('Supervision distante du transfert indisponible ou incomplete.') from exc
        if not isinstance(data, dict):
            raise SSHError('Observation distante du transfert invalide.')
        if not data.get('ok'):
            raise SSHError(data.get('error', 'Transfert distant refuse.'))
        return data

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

    def commit(self):
        self.process.stdin.write('{"action":"commit"}\n')
        self.process.stdin.flush()
        self.result = self._receive()
        return self.result

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
