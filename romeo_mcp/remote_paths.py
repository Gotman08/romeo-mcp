"""Confinement POSIX partage par les programmes executes sur ROMEO.

Les racines connues peuvent etre des alias GPFS. Apres resolution physique,
chaque composant est ouvert avec O_NOFOLLOW et conserve par des descripteurs :
une substitution de lien entre verification et ouverture echoue au lieu de
rediriger l'operation. Aucun module du paquet n'est requis sur le cluster.
"""
import json
import shlex

from .guard import GuardError, allowed_roots, personal_project_folder


def roots_for(connection):
    return allowed_roots(connection.home, connection.scratch, connection.path_aliases)


#: Attend `d` ; ne suit aucun lien et ne modifie qu'un dossier du compte courant.
LOCK_FOLDER = r'''if [ -L "$d" ]; then echo 'lien symbolique'; exit 3; fi
mkdir -m 700 -- "$d" 2>/dev/null
[ -d "$d" ] || { echo 'creation impossible'; exit 4; }
[ -O "$d" ] || { stat -c 'proprietaire %U' -- "$d"; exit 5; }
chmod u=rwx,g=,o=,g+s -- "$d" && stat -c %a -- "$d"'''


def ensure_private_folder(connection, path):
    """Cree si besoin le dossier personnel du login et le reserve a son compte.

    Appele avant chaque ecriture : un dossier rouvert entre-temps est refermé.
    `g+s` conserve le groupe du projet, seul a disposer d'un quota sous /project.
    """
    folder = personal_project_folder(path, connection)
    if folder is None:
        return
    result = connection.run("d={}\n{}".format(shlex.quote(folder), LOCK_FOLDER), timeout=25, max_chars=2000)
    observed = result.stdout.strip()
    if not result.ok or observed != "2700":
        raise GuardError(
            "dossier personnel {} non reserve a ton compte ({}). Aucune ecriture effectuee. "
            "Il doit etre un vrai dossier t'appartenant : s'il appartient a un autre compte, "
            "demande-lui ou a l'administrateur de te le transferer ou de le retirer."
            .format(folder, observed[:200] or "aucune reponse")
        )


CONFINED_PATHS = r'''
import os

def _inside(path, root):
    return path == root or path.startswith(root.rstrip('/') + '/')

def _directory(path):
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    current = os.open('/', flags)
    try:
        for part in path.split('/'):
            if part:
                next_fd = os.open(part, flags, dir_fd=current)
                os.close(current)
                current = next_fd
        return current
    except BaseException:
        os.close(current)
        raise

def _anchor(path, roots):
    physical = sorted({os.path.realpath(root) for root in roots}, key=len, reverse=True)
    root = next((root for root in physical if _inside(path, root)), None)
    if root is None:
        raise PermissionError('Cible physique hors des racines autorisees.')
    return root, _directory(root)

def confined_parent(path, roots):
    # Ne pas resoudre le dernier composant des ecritures : une cible existante
    # symbolique doit etre refusee, et non remplacer son fichier de destination.
    parent = os.path.realpath(os.path.dirname(path))
    root, current = _anchor(parent, roots)
    try:
        relative = os.path.relpath(parent, root)
        if relative != '.':
            for part in relative.split('/'):
                next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
                os.close(current)
                current = next_fd
        return current, os.path.basename(path)
    except BaseException:
        os.close(current)
        raise

def confined_open(path, roots, flags):
    target = os.path.realpath(path)
    # Valider aussi le fichier final, avant d'ouvrir son parent.
    root, anchor = _anchor(target, roots)
    if target == root:
        return anchor
    os.close(anchor)
    parent, name = confined_parent(target, roots)
    try:
        return os.open(name, flags | os.O_NOFOLLOW, dir_fd=parent)
    finally:
        os.close(parent)
'''


DIRECTORY_TARGET = '__ROMEO_CONFINED_TARGET__'
DIRECTORY_COMMAND = CONFINED_PATHS + r'''
import json, shlex, signal, subprocess, sys
request = json.loads(sys.argv[1])
directory = None
process = None
def interrupted(*args):
    raise RuntimeError('Inventaire distant interrompu.')

def stop():
    if process is not None and process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()

signal.signal(signal.SIGTERM, interrupted)
signal.signal(signal.SIGHUP, interrupted)
try:
    directory = confined_open(request['path'], request['roots'], os.O_RDONLY | os.O_DIRECTORY)
    proxy = '/proc/{}/fd/{}/.'.format(os.getpid(), directory)
    command = request['command'].replace('__ROMEO_CONFINED_TARGET__', shlex.quote(proxy))
    process = subprocess.Popen(['bash', '-c', command], stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, start_new_session=True)
    try:
        output, _ = process.communicate(timeout=request['timeout'])
    except subprocess.TimeoutExpired:
        stop()
        raise TimeoutError('Inventaire distant interrompu : delai depasse.')
    text = output.decode('utf-8', 'replace').replace(proxy, request['path'])
    print(text, end='')
    sys.exit(process.returncode)
except (OSError, ValueError, RuntimeError) as exc:
    print(json.dumps({'ok': False, 'error': str(exc)[:500]}))
    sys.exit(2)
finally:
    stop()
    if process is not None and process.stdout is not None:
        process.stdout.close()
    if directory is not None:
        os.close(directory)
'''


def directory_command(connection, path, command, timeout):
    """Lie un inventaire en lecture seule au repertoire autorise pendant tout son parcours."""
    request = json.dumps(dict(path=path, roots=roots_for(connection), command=command, timeout=timeout))
    return 'python3 -c {} {}'.format(shlex.quote(DIRECTORY_COMMAND), shlex.quote(request))
