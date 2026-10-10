"""Confinement POSIX partage par les programmes executes sur ROMEO.

Les racines connues peuvent etre des alias GPFS. Apres resolution physique,
chaque composant est ouvert avec O_NOFOLLOW et conserve par des descripteurs :
une substitution de lien entre verification et ouverture echoue au lieu de
rediriger l'operation. Aucun module du paquet n'est requis sur le cluster.
"""
from .guard import allowed_roots


def roots_for(connection):
    return allowed_roots(connection.home, connection.scratch, connection.path_aliases)


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
