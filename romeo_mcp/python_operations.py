"""Preparation d'operations Python sur un noeud de l'architecture demandee."""
import posixpath
import shlex

from .execution_backend import _contexte_chemins
from .cluster import ARCHS, ClusterError, require_account
from .guard import check_path
from .plans import prepare_spec
from .slurm import JobSpec
from .ssh import session


def _paths(env_path=None):
    require_account()
    s = session()
    context = _contexte_chemins(s, False)
    home, scratch, aliases, _ = context
    env = check_path(env_path, home, scratch, aliases) if env_path else None
    return s, context, env


def _requirement(value):
    if not value.strip() or value.startswith('-') or any(c in value for c in ('\n', '\r', '\x00')):
        raise ValueError('Specification de paquet vide ou invalide.')
    return shlex.quote(value)


def _wheelhouse(scratch, arch):
    if arch not in ARCHS:
        raise ClusterError('Architecture inconnue : ' + arch)
    return posixpath.join(scratch, '.wheels', ARCHS[arch]['uname'])


def prepare_environment(env_path, arch, time_limit, spack_packages):
    if not spack_packages or any(spec.strip() == 'python' for spec in spack_packages):
        raise ValueError("Choisis une specification Python Spack non ambigue dans spack_packages "
                         "(version, compilateur ou empreinte), apres romeo_software pour l'architecture "
                         "voulue. Le nom 'python' seul correspond a plusieurs installations sur ROMEO.")
    s, context, env = _paths(env_path)
    quoted = shlex.quote(env)
    command = 'mkdir -- {0} || exit 1\npython3 -m venv {0}'.format(quoted)
    return prepare_spec('python_env', JobSpec(name='mcp-python-env', command=command, arch=arch,
        time=time_limit, cpus_per_task=4, spack_packages=spack_packages), details={'env_path': env},
        connection=s, context=context)


def prepare_packages(env_path, packages, arch, time_limit, upgrade):
    if not packages or len(packages) > 100:
        raise ValueError('Choisis entre 1 et 100 paquets.')
    s, context, env = _paths(env_path)
    wheelhouse = _wheelhouse(context[1], arch)
    interpreter = shlex.quote(posixpath.join(env, 'bin', 'python'))
    command = 'test -f {} && test -x {} || exit 1\n{} -m pip install --find-links {} {} -- {}'.format(
        shlex.quote(posixpath.join(env, 'pyvenv.cfg')), interpreter, interpreter, shlex.quote(wheelhouse),
        '--upgrade' if upgrade else '', ' '.join(_requirement(p) for p in packages))
    return prepare_spec('python_packages', JobSpec(name='mcp-python-install', command=command, arch=arch,
        time=time_limit, cpus_per_task=16), details={'env_path': env, 'wheelhouse': wheelhouse},
        connection=s, context=context)


def prepare_wheel(source, arch, time_limit, cpus, with_gpu, spack_packages, no_build_isolation):
    s, context, _ = _paths()
    wheelhouse = _wheelhouse(context[1], arch)
    command = 'mkdir -p {}\npython3 -m pip wheel --no-deps --wheel-dir {} {} -- {}'.format(
        shlex.quote(wheelhouse), shlex.quote(wheelhouse),
        '--no-build-isolation' if no_build_isolation else '', _requirement(source))
    return prepare_spec('python_wheel', JobSpec(name='mcp-python-wheel', command=command, arch=arch,
        time=time_limit, cpus_per_task=cpus, gpus_per_node=int(with_gpu),
        spack_packages=(spack_packages or []) + ['py-pip', 'py-wheel', 'py-setuptools']),
        details={'wheelhouse': wheelhouse, 'source': source}, connection=s, context=context)
