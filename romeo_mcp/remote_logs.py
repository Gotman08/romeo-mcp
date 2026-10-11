"""Lecteur POSIX de journaux : motifs transmis en JSON, ouvertures confinees."""
from .remote_paths import CONFINED_PATHS


READ_LOGS = CONFINED_PATHS + r'''
import fnmatch, heapq, json, signal, stat, subprocess, sys
request = json.loads(sys.argv[1])
roots = request['roots']
budget, lines = request['max_chars'], request['lines']
pattern = request['pattern']
process = None

def interrupted(*args):
    raise RuntimeError('Lecture des journaux interrompue.')

signal.signal(signal.SIGTERM, interrupted)
signal.signal(signal.SIGHUP, interrupted)

def grep(data):
    global process
    try:
        process = subprocess.Popen(['grep', '-aE', '-m', str(lines), '--', pattern],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output, error = process.communicate(data, timeout=5)
        if process.returncode not in (0, 1):
            raise ValueError('Motif de recherche invalide : ' + error.decode('utf-8', 'replace')[:400])
        return output
    finally:
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.communicate()
            process = None

def regular(path):
    descriptor = confined_open(path, roots, os.O_RDONLY | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise OSError('La cible doit etre un fichier regulier ; les fichiers speciaux sont refuses.')
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise

def selected(path, probe=False):
    if not path:
        return [], False, False
    parent, name = os.path.dirname(path), os.path.basename(path)
    try:
        directory = confined_open(parent, roots, os.O_RDONLY | os.O_DIRECTORY)
    except FileNotFoundError:
        return [], False, False
    nonempty = False
    try:
        def matches(scan):
            nonlocal nonempty
            for entry in scan:
                if entry.name != name and not fnmatch.fnmatchcase(entry.name, name):
                    continue
                if entry.is_dir(follow_symlinks=False):
                    continue
                target = os.path.join(parent, entry.name)
                if probe and not nonempty:
                    descriptor = regular(target)
                    try:
                        nonempty = os.fstat(descriptor).st_size > 0
                    finally:
                        os.close(descriptor)
                yield target
        with os.scandir(directory) as scan:
            paths = heapq.nsmallest(request['max_files'] + 1, matches(scan))
        return paths[:request['max_files']], len(paths) > request['max_files'], nonempty
    finally:
        os.close(directory)

def tail(descriptor):
    # Lire depuis la fin, sans materialiser une ligne de plusieurs Go.
    end = os.fstat(descriptor).st_size
    trailing = end > 0 and os.pread(descriptor, 1, end - 1) == b'\n'
    wanted = lines + int(trailing)
    pieces, count, kept = [], 0, 0
    cap = 4 * (budget + 1)
    while end > 0 and count < wanted and kept < cap:
        size = min(65536, end, cap - kept)
        end -= size
        block = os.pread(descriptor, size, end)
        pieces.append(block)
        count += block.count(b'\n')
        kept += len(block)
    raw = b''.join(reversed(pieces))
    raw = b'\n'.join(raw.split(b'\n')[-wanted:])
    return raw, end > 0 and count < wanted

try:
    if pattern is not None:
        grep(b'')  # grep=1 est une absence de match ; grep=2 un motif invalide.
    logs = {'err': '', 'out': ''}
    clipped = {'err': False, 'out': False}
    files_limited = False
    has_stderr_content = False
    for label in ('err', 'out'):
        paths, limited, nonempty = selected(request['targets'].get(label), probe=label == 'err')
        if label == 'err':
            has_stderr_content = nonempty
        if request['stream'] in ('err', 'out') and request['stream'] != label:
            continue
        files_limited = files_limited or limited
        for path in paths:
            descriptor = regular(path)
            try:
                if pattern is None:
                    raw, cut = tail(descriptor)
                else:
                    size = os.fstat(descriptor).st_size
                    raw = grep(os.pread(descriptor, request['max_bytes_per_file'],
                                        max(0, size - request['max_bytes_per_file'])))
                    cut = False
            finally:
                os.close(descriptor)
            text = raw.decode('utf-8', 'replace').rstrip()
            if text.strip():
                name = os.fsencode(path).decode('utf-8', 'replace')
                combined = logs[label] + ('\n' if logs[label] else '') + '--- ' + name + '\n' + text
                clipped[label] = clipped[label] or cut or len(combined) > budget
                logs[label] = combined[-budget:]
    print(json.dumps(dict(logs=logs, clipped=clipped, files_limited=files_limited,
                          has_stderr_content=has_stderr_content), ensure_ascii=True))
except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
    print(json.dumps({'error': str(exc)[:500]}, ensure_ascii=True))
    sys.exit(2)
'''
