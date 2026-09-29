"""Operations de fichiers et controle de chemins, sans interface MCP."""
import base64
import json
import re
import shlex

from .guard import allowed_roots, check_path


# Execute par Python sur le login. Le verrou est partage entre les processus
# MCP ; une publication atomique ne laisse jamais voir un fichier incomplet.
_WRITE = r'''
import base64, fcntl, hashlib, json, os, stat, sys, tempfile
request = json.loads(sys.argv[1])
path = request['path']
parent = os.path.dirname(path)
temp = None
try:
    if not os.path.isdir(parent):
        raise ValueError('Le repertoire parent doit exister.')
    lock_fd = os.open(os.path.join(parent, '.romeo-mcp-files.lock'),
                      os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lock_fd, 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        exists = os.path.lexists(path)
        mode = 0o600
        if request['action'] == 'create':
            if exists:
                raise ValueError('La cible existe deja ; utilise file_replace.')
        else:
            if not exists or not stat.S_ISREG(os.lstat(path).st_mode):
                raise ValueError('La cible doit etre un fichier regulier existant, sans lien symbolique.')
            mode = stat.S_IMODE(os.lstat(path).st_mode)
            expected = request.get('expected')
            if expected:
                digest = hashlib.sha256()
                with open(path, 'rb') as current:
                    for block in iter(lambda: current.read(1048576), b''):
                        digest.update(block)
                if digest.hexdigest() != expected:
                    raise ValueError('Empreinte differente : le fichier a change. Relis-le avant de remplacer.')
        data = base64.b64decode(request['content'])
        fd, temp = tempfile.mkstemp(prefix='.romeo-write-', dir=parent)
        with os.fdopen(fd, 'wb') as output:
            os.fchmod(output.fileno(), mode)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        if request['action'] == 'create':
            os.link(temp, path)
        else:
            os.replace(temp, path)
            temp = None
        print(json.dumps({'ok': True, 'path': path, 'bytes': len(data),
                          'sha256': hashlib.sha256(data).hexdigest(), 'action': request['action']}))
except (OSError, ValueError) as exc:
    print(json.dumps({'ok': False, 'error': str(exc)}))
finally:
    if temp is not None:
        os.unlink(temp)
'''


def _write(connection, path, content, action, expected=None):
    if expected is not None and not re.fullmatch(r'[0-9a-fA-F]{64}', expected):
        raise ValueError('expected_sha256 doit contenir 64 caracteres hexadecimaux.')
    raw = content.encode('utf-8')
    if len(raw) > 65536:
        raise ValueError('Contenu texte limite a 64 Kio par appel.')
    target = check_path(path, connection.home, connection.scratch, connection.path_aliases)
    request = json.dumps({'path': target, 'content': base64.b64encode(raw).decode(),
                          'action': action, 'expected': expected.lower() if expected else None})
    response = connection.run('python3 -c {} {}'.format(shlex.quote(_WRITE), shlex.quote(request)),
                              timeout=60, max_chars=4000)
    if not response.ok or response.truncated:
        return {'ok': False, 'error': 'Ecriture distante non confirmee : relis la cible avant de reessayer.'}
    return json.loads(response.stdout)


def create_file(connection, path: str, content: str) -> dict:
    return _write(connection, path, content, 'create')


def replace_file(connection, path: str, content: str, expected_sha256=None) -> dict:
    return _write(connection, path, content, 'replace', expected_sha256)


def check_script_paths(connection, script: str) -> dict:
    if not script.strip():
        raise ValueError('script vide')
    roots = [r for r in allowed_roots(connection.home, connection.scratch, connection.path_aliases)
             if r not in ('/tmp', '/apps')]
    # Analyse lexicale uniquement : aucune expansion ni execution du script.
    tokens = shlex.split(script, comments=False)
    candidates = set()
    dynamic = []
    for token in tokens:
        candidate = token.split('=', 1)[-1].rstrip(';,)')
        if not candidate.startswith('/'):
            continue
        if any(symbol in candidate for symbol in ('$', '`', '*', '?', '%')):
            dynamic.append(candidate)
        elif any(candidate == root or candidate.startswith(root.rstrip('/') + '/') for root in roots):
            candidates.add(candidate)
    paths = sorted(candidates)
    checked = paths[:20]
    code = 'import json,os,sys; print(json.dumps([{ "path": p, "exists": os.path.exists(p)} for p in json.loads(sys.argv[1])]))'
    result = connection.run('python3 -c {} {}'.format(shlex.quote(code), shlex.quote(json.dumps(checked))),
                            timeout=30, max_chars=16000)
    if not result.ok or result.truncated:
        return {'ok': False, 'error': 'Verification distante incomplete ou indisponible.'}
    return {'ok': True, 'paths': json.loads(result.stdout), 'unchecked': paths[20:],
            'dynamic_paths': sorted(set(dynamic)), 'scope': 'remote_literal_paths',
            'note': "Analyse lexicale limitee aux racines autorisees ; un chemin de sortie peut legitimement ne pas exister."}
