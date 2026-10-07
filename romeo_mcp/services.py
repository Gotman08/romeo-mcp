"""Cycle de vie des services interactifs, independant du protocole MCP."""
import json
import posixpath
import re
import shlex
import uuid
from urllib.parse import quote

from .cluster import require_account
from .ssh import SSHError
from .execution_backend import _contexte_chemins
from .guard import check_path
from .plans import prepare_spec, _submission_target
from .registry import registry
from .slurm import JobSpec
from .ssh import session


def prepare_service(config: dict, time_limit: str, arch: str, gpus: int,
                    cpus: int, workdir: str | None, spack_packages: list[str] | None) -> dict:
    require_account()
    s = session()
    home, scratch, aliases, offline = _contexte_chemins(s, False)
    env = check_path(config['env_path'], home, scratch, aliases)
    port = config['port']
    kind = config['service']
    directory = posixpath.join(scratch, '.romeo-services', uuid.uuid4().hex)
    credential = posixpath.join(directory, 'token') if kind in {'jupyter', 'vllm'} else None
    python = shlex.quote(posixpath.join(env, 'bin', 'python'))
    prefix = ['umask 077', 'mkdir -p {}'.format(shlex.quote(directory))]
    if credential:
        prefix.append('{} -c {} > {}'.format(python, shlex.quote('import secrets; print(secrets.token_urlsafe(32))'),
                                               shlex.quote(credential)))
    token = '"$(cat {})"'.format(shlex.quote(credential)) if credential else ''
    binary = lambda name: shlex.quote(posixpath.join(env, 'bin', name))
    if kind == 'jupyter':
        command = '{} lab --no-browser --ip=0.0.0.0 --port={} --ServerApp.port_retries=0 --ServerApp.token={}'.format(binary('jupyter'), port, token)
        health_path = '/api/status'
    elif kind == 'tensorboard':
        logdir = check_path(config['logdir'], home, scratch, aliases)
        command = '{} --logdir {} --host 0.0.0.0 --port {}'.format(binary('tensorboard'), shlex.quote(logdir), port)
        health_path = '/'
    elif kind == 'vllm':
        if gpus < 1:
            raise ValueError('vLLM exige au moins un GPU.')
        command = '{} serve {} --host 0.0.0.0 --port {} --api-key {}'.format(binary('vllm'), shlex.quote(config['model']), port, token)
        health_path = '/health'
    else:
        command = '{} ui --host 0.0.0.0 --port {}'.format(binary('mlflow'), port)
        health_path = '/health'
    spec = JobSpec(name='mcp-' + kind, command='\n'.join([*prefix, 'exec ' + command]), time=time_limit,
                   arch=arch, gpus_per_node=gpus, cpus_per_task=cpus, workdir=workdir,
                   spack_packages=spack_packages or [], redirect_caches=(kind == 'vllm'))
    result = prepare_spec('service', spec, details={'service': {
        'type': kind, 'port': port, 'health_path': health_path, 'credential_path': credential,
        'authentication': 'token' if credential else 'none', 'env_path': env},
        'warnings': [] if credential else ['Ce service sans authentification ecoute sur le reseau du noeud. Acces via un tunnel SSH a ouvrir manuellement.']},
        connection=s, context=(home, scratch, aliases, offline))
    return result


def _service(service_id):
    saved = registry().prepared_submission(service_id)
    if not saved or saved['payload']['kind'] != 'service':
        raise ValueError('Service introuvable.')
    job_id = (saved['result'] or {}).get('job_id')
    if not job_id:
        raise ValueError('Ce plan ne possede aucun demarrage confirme ; consulte plan_get avant toute nouvelle tentative.')
    s = session()
    home, scratch, _, _ = _contexte_chemins(s, True)
    if saved['payload']['target'] != _submission_target(s, home, scratch):
        raise ValueError('La cible SSH ou le compte ont change depuis la preparation.')
    return s, job_id, saved['payload']['preview']['service']


def allocation_state(s, job_id: str) -> dict:
    if not re.fullmatch(r'\d+', job_id):
        raise ValueError('job_id invalide')
    result = s.run("squeue -h -j {} -o '%T|%N'".format(job_id), timeout=20, max_chars=4000)
    if not result.ok or result.truncated:
        return {'ok': False, 'job_id': job_id, 'state': 'unknown', 'error': 'Etat Slurm indisponible.'}
    line = result.stdout.strip().splitlines()
    if not line:
        result = s.run('sacct -nP -j {} -o JobID,State,NodeList'.format(job_id), timeout=20, max_chars=4000)
        if not result.ok or result.truncated:
            return {'ok': False, 'job_id': job_id, 'state': 'unknown', 'error': 'Comptabilite Slurm indisponible.'}
        line = [row[len(job_id)+1:] for row in result.stdout.splitlines() if row.startswith(job_id + '|')]
    if not line:
        return {'ok': True, 'job_id': job_id, 'state': 'unknown', 'node': None}
    parts = line[0].split('|')
    state = parts[0].strip().split()[0].rstrip('+')
    node = parts[1].strip() if len(parts) > 1 else ''
    if state in {'PENDING', 'CONFIGURING', 'REQUEUED'}:
        phase = 'waiting'
    elif state == 'RUNNING':
        phase = 'starting'
    elif state in {'CANCELLED', 'COMPLETED'}:
        phase = 'stopped'
    elif state in {'FAILED', 'TIMEOUT', 'NODE_FAIL', 'OUT_OF_MEMORY', 'BOOT_FAIL', 'DEADLINE', 'PREEMPTED'}:
        phase = 'failed'
    else:
        phase = 'unknown'
    return {'ok': True, 'job_id': job_id, 'state': phase, 'slurm_state': state,
            'node': node if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]*', node) else None}


_PROBE = '''import json,sys,urllib.request
config=json.loads(sys.argv[1])
headers={}
if config['credential_path']:
    with open(config['credential_path']) as stream: token=stream.read().strip()
    headers['Authorization']=('token ' if config['type']=='jupyter' else 'Bearer ')+token
request=urllib.request.Request(sys.argv[2], headers=headers)
with urllib.request.urlopen(request, timeout=3) as response:
    print('READY' if response.status==200 else 'STARTING')
'''


def service_status(service_id: str) -> dict:
    saved = registry().prepared_submission(service_id)
    target = saved["payload"]["target"] if saved else None
    job_id = (saved["result"] or {}).get("job_id") if saved else None
    target_checked = False
    try:
        s, job_id, config = _service(service_id)
        # _service compared this target to the current host/account/roots.
        # Reuse that evidence instead of another remote identity lookup.
        target_checked = True
        state = _observe_service(s, job_id, config, service_id)
    except SSHError as exc:
        state = {"ok": False, "state": "unknown", "service_id": service_id, "job_id": job_id,
                 "error": str(exc)}
    state["target_checked"] = target_checked
    state["current_state_observed"] = state["ok"] and state["state"] != "unknown"
    if state["ok"] and state["state"] != "unknown":
        state["observation"] = registry().save_observation(job_id, target, state)
    else:
        state["last_observation"] = registry().observation(job_id, target)
    state["service_readiness_observed"] = state["state"] == "ready"
    return state


def _observe_service(s, job_id, config, service_id):
    state = {**allocation_state(s, job_id), 'service_id': service_id}
    if state['state'] == 'starting' and state.get('node'):
        url = 'http://{}:{}{}'.format(state['node'], config['port'], config['health_path'])
        result = s.run('python3 -c {} {} {}'.format(shlex.quote(_PROBE), shlex.quote(json.dumps(config)), shlex.quote(url)),
                       timeout=10, max_chars=2000)
        if result.ok and not result.truncated and result.stdout.strip() == 'READY':
            state['state'] = 'ready'
        else:
            state['readiness'] = 'Sonde HTTP non concluante ; le job peut encore demarrer.'
    return state


def connection_info(service_id: str, local_port: int) -> dict:
    if not 1024 <= local_port <= 65535:
        raise ValueError('local_port doit etre compris entre 1024 et 65535.')
    state = service_status(service_id)
    if state['state'] != 'ready':
        return {**state, 'ok': False, 'error': 'Le service doit etre pret avant de fournir son acces.'}
    s, _, config = _service(service_id)
    url = 'http://localhost:{}/'.format(local_port)
    token = None
    if config['credential_path']:
        response = s.run('head -c 256 -- {}'.format(shlex.quote(config['credential_path'])), timeout=10, max_chars=256)
        if not response.ok or response.truncated or not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', response.stdout.strip()):
            raise ValueError('Identifiant du service indisponible.')
        token = response.stdout.strip()
        if config['type'] == 'jupyter':
            url += '?token=' + quote(token)
    tunnel = 'ssh -N -L {}:{}:{} {}'.format(local_port, state['node'], config['port'], shlex.quote(s.host))
    return {'ok': True, 'service_id': service_id, 'job_id': state['job_id'], 'url': url,
            'tunnel_command': tunnel, 'tunnel_opened': False, 'authentication': config['authentication'],
            **({'api_key': token} if config['type'] == 'vllm' else {})}


def stop_service(service_id: str) -> dict:
    s, job_id, _ = _service(service_id)
    result = s.run('scancel {}'.format(job_id), timeout=20, max_chars=4000)
    return {'ok': result.ok, 'service_id': service_id, 'job_id': job_id,
            'stop_requested': result.ok, 'next_step': 'Consulte service_status pour confirmer la fin.'}
