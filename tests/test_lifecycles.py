"""Contrats des cycles de vie, fichiers atomiques et releves immuables, sans SSH."""
import asyncio
import builtins
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
import shlex
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import offline
import test_job_io as io
from romeo_mcp import server as assembled, noyau, plans, services, python_operations, workload_preparation
from romeo_mcp import outils_execution as execution, outils_donnees as data, outils_mesure as measure
from romeo_mcp import outils_calcul as jobs, reproducibility as repro, file_operations
from romeo_mcp.registry import Registry
from romeo_mcp.ssh import Result
from romeo_mcp.validation import blocking_problems


class Contracts(unittest.TestCase):
    def test_catalog_has_one_action_per_tool_and_explicit_effects(self):
        with patch.object(noyau.server, 'tool_profile', 'expert'):
            tools = {t.name: t for t in asyncio.run(noyau.server.list_tools())}
        old = ('launch_interactive_service', 'spawn_remote_workspace', 'write_remote_file', 'sbatch_lint',
               'export_job_report', 'build_on_node', 'submit_resilient_job', 'profile_job', 'stage_dataset',
               'build_wheel', 'romeo_pip_install', 'allocate_debug_node')
        self.assertTrue(all(name not in tools for name in old))
        for name in ('service_start', 'python_env_create', 'python_packages_install', 'python_wheel_build',
                     'dataset_download', 'job_profile_submit', 'job_resilient_submit', 'cluster_allocation_start',
                     'compute_command_run'):
            self.assertEqual(set(tools[name].input_schema['properties']), {'plan_id', 'confirm'})
            self.assertFalse(tools[name].annotations.read_only_hint)
        for name, tool in tools.items():
            if name.endswith('_prepare'):
                self.assertNotIn('confirm', tool.input_schema['properties'])
        self.assertTrue(tools['file_replace'].annotations.destructive_hint)
        for name in ('sbatch_validate', 'sbatch_check_paths', 'plan_get', 'service_status', 'service_connection_info', 'job_report_get'):
            self.assertTrue(tools[name].annotations.read_only_hint)
        self.assertEqual(set(tools['job_report_export'].input_schema['properties']), {'report_id', 'output_dir'})

    def test_expert_is_discovery_only_and_full_has_no_escape_hatches(self):
        with patch.object(noyau.server, 'tool_profile', 'full'):
            full = {t.name for t in asyncio.run(noyau.server.list_tools())}
        with patch.object(noyau.server, 'tool_profile', 'expert'):
            expert = {t.name for t in asyncio.run(noyau.server.list_tools())}
        self.assertEqual(expert - full, {'compute_command_prepare', 'compute_command_run', 'login_command_run'})

    def test_local_validation_cannot_open_a_session(self):
        with patch.object(data, 'session', side_effect=AssertionError('SSH interdit')):
            result = data.sbatch_validate('#!/bin/bash\n#SBATCH --mem=4G\ncat /home/user/missing\n')
        self.assertTrue(result['ok'])
        self.assertFalse(any('inexistant' in c['message'] for c in result['constats']))
        self.assertTrue(blocking_problems('#!/bin/bash\necho hello\n#SBATCH --mem=4G'))

    def test_service_configuration_rejects_irrelevant_and_missing_options(self):
        for config in ({'service': 'jupyter', 'env_path': '/tmp/env', 'model': 'wrong'},
                       {'service': 'vllm', 'env_path': '/tmp/env'},
                       {'service': 'tensorboard', 'env_path': '/tmp/env'},
                       {'service': 'grafana', 'env_path': '/tmp/env'}):
            with patch.object(services, 'session', side_effect=AssertionError('aucun SSH')):
                self.assertFalse(execution.service_prepare(config)['ok'])


class PythonEnvironmentTests(unittest.TestCase):
    def test_missing_or_ambiguous_python_is_rejected_before_ssh_or_plan_creation(self):
        with patch.object(python_operations, '_paths') as paths, \
             patch.object(python_operations, 'prepare_spec') as prepare:
            for packages in (None, [], ['python'], [' python ']):
                with self.subTest(packages=packages), self.assertRaisesRegex(ValueError, 'non ambigue'):
                    python_operations.prepare_environment('/scratch_p/user/env', 'x64cpu', '1m', packages)
            paths.assert_not_called()
            prepare.assert_not_called()


@unittest.skipUnless(io.BASH, 'Bash requis')
class PlansAndServices(unittest.TestCase):
    setUp = io.JobIOTests.setUp

    def patch_operations(self):
        for module in (services, python_operations, execution):
            self.enterContext(patch.object(module, 'session', return_value=self.session))
        self.enterContext(patch.object(services, 'registry', return_value=self.store))

    def test_every_new_preparation_freezes_an_executable_script_and_replays_once(self):
        self.patch_operations()
        env = self.session.scratch + '/venv'
        preparations = [
            (lambda: execution.service_prepare({'service': 'jupyter', 'env_path': env}, arch='x64cpu'), execution.service_start),
            (lambda: execution.python_env_prepare(env, arch='x64cpu', spack_packages=['python@3.13.5']), execution.python_env_create),
            (lambda: execution.python_packages_prepare(env, ['example-package==1.0'], arch='x64cpu'), execution.python_packages_install),
            (lambda: execution.python_wheel_prepare('example-package==1.0', arch='x64cpu'), execution.python_wheel_build),
            (lambda: execution.cluster_allocation_prepare(arch='x64cpu', gpus_per_node=0), execution.cluster_allocation_start),
            (lambda: execution.compute_command_prepare(['echo hello'], arch='x64cpu'), execution.compute_command_run),
            (lambda: data.dataset_prepare('https://example.org/data.txt', self.session.scratch + '/data'), data.dataset_download),
            (lambda: measure.job_profile_prepare('echo hello', arch='armgpu'), measure.job_profile_submit),
        ]
        for prepare, submit in preparations:
            before = len(self.session.pending)
            result = prepare()
            self.assertTrue(result['ok'], result)
            self.assertEqual(len(self.session.pending), before)
            self.assertEqual(blocking_problems(result['script']), [], result['script'])
            reread = jobs.plan_get(result['plan_id'])
            self.assertEqual(reread['plan']['entries'][0]['plan']['script'], result['script'])
            self.assertEqual(reread['state'], 'ready')
            self.assertFalse(submit(result['plan_id'])['ok'])
            with patch.object(plans, 'plan_job', side_effect=AssertionError('aucune regeneration')):
                started = submit(result['plan_id'], confirm=True)
                self.assertTrue(started['ok'], started)
                replay = submit(result['plan_id'], confirm=True)
            self.assertEqual(started['job_id'], replay['job_id'])
            self.assertEqual(len(self.session.pending), before + 1)
            self.assertEqual(self.session.pending[-1][1].read_text(encoding='utf-8'), result['script'])
            self.assertEqual(jobs.plan_get(result['plan_id'])['state'], 'submitted')

    def prepare_service(self):
        self.patch_operations()
        result = execution.service_prepare({'service': 'jupyter', 'env_path': self.session.scratch + '/venv'}, arch='x64cpu')
        self.assertTrue(result['ok'], result)
        started = execution.service_start(result['plan_id'], confirm=True)
        self.assertTrue(started['ok'], started)
        self.assertEqual(started['service_id'], result['plan_id'])
        return started

    def test_offline_paths_are_resolved_once_and_cannot_become_executable(self):
        self.patch_operations()
        context = ('/home/user', '/scratch_p/user', [], 'hors ligne')
        for module, prepare in (
            (services, lambda: execution.service_prepare({'service': 'jupyter', 'env_path': '/scratch_p/user/env'})),
            (python_operations, lambda: execution.python_env_prepare('/scratch_p/user/env', spack_packages=['python@3.13.5'])),
            (python_operations, lambda: execution.python_packages_prepare('/scratch_p/user/env', ['example'])),
            (python_operations, lambda: execution.python_wheel_prepare('example')),
        ):
            with patch.object(module, '_contexte_chemins', return_value=context) as roots:
                result = prepare()
            self.assertTrue(result['ok'], result)
            self.assertIsNone(result['plan_id'])
            self.assertFalse(result['submittable'])
            roots.assert_called_once()

    def test_service_start_never_waits_and_status_requires_http_readiness(self):
        started = self.prepare_service()
        for slurm, probe, expected in [('PENDING|', '', 'waiting'), ('RUNNING|node-01', '', 'starting'),
                                        ('RUNNING|node-01', 'READY', 'ready'), ('FAILED|node-01', '', 'failed'),
                                        ('CANCELLED|node-01', '', 'stopped')]:
            def run(command, **kwargs):
                self.assertNotIn('srun', command)
                if command.startswith('squeue '):
                    return Result(0, slurm, 0)
                self.assertTrue(command.startswith('python3 -c '), command)
                return Result(0, probe, 0)
            with patch.object(self.session, 'run', side_effect=run):
                result = execution.service_status(started['service_id'])
            self.assertEqual(result['state'], expected)

    def test_service_connection_requires_ready_and_never_opens_a_tunnel(self):
        started = self.prepare_service()
        with patch.object(self.session, 'run', return_value=Result(0, 'PENDING|', 0)):
            self.assertFalse(execution.service_connection_info(started['service_id'])['ok'])
        calls = []
        def run(command, **kwargs):
            calls.append(command)
            if command.startswith('squeue '): return Result(0, 'RUNNING|node-01', 0)
            if command.startswith('python3 '): return Result(0, 'READY', 0)
            if command.startswith('head '): return Result(0, 'a' * 43, 0)
            raise AssertionError(command)
        self.session.host = plans.DEFAULT_HOST
        with patch.object(self.session, 'run', side_effect=run):
            result = execution.service_connection_info(started['service_id'], local_port=9000)
        self.assertTrue(result['ok'], result)
        self.assertFalse(result['tunnel_opened'])
        self.assertIn('9000:node-01:8888', result['tunnel_command'])
        self.assertIn('?token=', result['url'])
        self.assertFalse(any(c.startswith('ssh ') for c in calls))
        with patch.object(self.session, 'run', return_value=Result(0, '', 0)) as run_stop:
            self.assertTrue(execution.service_stop(started['service_id'])['stop_requested'])
        self.assertEqual(run_stop.call_args.args[0], 'scancel ' + started['job_id'])

    def test_sbatch_paths_are_remote_and_failures_are_not_a_clean_verdict(self):
        with patch.object(data, 'session', return_value=self.session):
            with patch.object(self.session, 'run', return_value=Result(1, 'SSH failed', 0)):
                self.assertFalse(data.sbatch_check_paths('cat ' + self.session.scratch + '/missing')['ok'])
            def run(command, **kwargs):
                paths = json.loads(shlex.split(command)[-1])
                return Result(0, json.dumps([{'path': p, 'exists': False} for p in paths]), 0)
            with patch.object(self.session, 'run', side_effect=run):
                result = data.sbatch_check_paths('cat "' + self.session.scratch + '/with spaces" "$HOME/dynamic"')
        self.assertTrue(result['ok'])
        self.assertFalse(result['paths'][0]['exists'])


class Reports(unittest.TestCase):
    def test_snapshot_survives_restart_and_exports_exactly_without_ssh(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Registry(Path(temp) / 'jobs.db')
            store.record('123', 'test', 'instant', 'x64cpu', '/scratch_p/user', '', '', '#!/bin/bash\necho hi')
            report = repro.collect_report('123', live=False, job_registry=store)
            store.close()
            store = Registry(Path(temp) / 'jobs.db')
            try:
                with patch.object(repro, 'session', side_effect=AssertionError('aucun SSH')):
                    first = repro.export_snapshot(report['report_id'], output_dir=temp, job_registry=store)
                    second = repro.export_snapshot(report['report_id'], output_dir=temp, job_registry=store)
                    self.assertEqual(Path(first['files']['report.json']).read_bytes(), Path(second['files']['report.json']).read_bytes())
                    self.assertEqual(first['created_at'], report['created_at'])
                with store._conn:
                    store._conn.execute("UPDATE report_snapshots SET payload = '{}' WHERE report_id = ?", (report['report_id'],))
                with self.assertRaisesRegex(ValueError, 'altere'):
                    repro.export_snapshot(report['report_id'], output_dir=temp, job_registry=store)
            finally:
                store.close()


class Files(unittest.TestCase):
    def test_create_replace_and_parallel_compare_and_swap_on_real_files(self):
        # Le programme distant POSIX est execute sur de vrais fichiers. Sous
        # Windows seuls flock et fchmod sont adaptes ; link/replace restent reels.
        with tempfile.TemporaryDirectory() as temp:
            target = str(Path(temp) / 'script.txt')
            lock = threading.Lock()
            class LocalPython:
                home = scratch = '/tmp'
                path_aliases = []
                def run(self, command, **kwargs):
                    _, _, code, request = shlex.split(command)
                    request = json.loads(request)
                    request['path'] = target
                    output = []
                    imports = {'sys': SimpleNamespace(argv=['program', json.dumps(request)])}
                    if os.name == 'nt':
                        imports['fcntl'] = SimpleNamespace(LOCK_EX=1, flock=lambda *_: None)
                        imports['os'] = SimpleNamespace(**{**vars(os), 'O_NOFOLLOW': 0, 'fchmod': lambda *_: None})
                    def importer(name, *args, **kwargs):
                        return imports[name] if name in imports else builtins.__import__(name, *args, **kwargs)
                    with lock if os.name == 'nt' else nullcontext():
                        exec(compile(code, '<remote-file-operation>', 'exec'), {'__builtins__': {
                            **vars(builtins), '__import__': importer, 'print': output.append}})
                    return Result(0, '\n'.join(output), 0)
            conn = LocalPython()
            created = file_operations.create_file(conn, '/tmp/script.txt', 'original')
            self.assertTrue(created['ok'], created)
            self.assertFalse(file_operations.create_file(conn, '/tmp/script.txt', 'overwrite')['ok'])
            self.assertEqual(Path(target).read_text(), 'original')
            self.assertFalse(file_operations.replace_file(conn, '/tmp/script.txt', 'wrong', '0' * 64)['ok'])
            digest = hashlib.sha256(b'original').hexdigest()
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda content: file_operations.replace_file(conn, '/tmp/script.txt', content, digest), ['A', 'B']))
            self.assertEqual(sum(r['ok'] for r in results), 1)
            self.assertIn(Path(target).read_text(), ('A', 'B'))
            Path(target).unlink()
            self.assertFalse(file_operations.replace_file(conn, '/tmp/script.txt', 'missing')['ok'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
