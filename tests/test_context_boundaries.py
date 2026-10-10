"""Regressions #26, #27, #30, #31 et #32, sans commande distante."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import subprocess
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import offline
from mcp import ClientSession, StdioServerParameters, stdio_client
from romeo_mcp import noyau, outils_calcul as jobs, outils_contexte as context, privacy, reproducibility
from romeo_mcp.errors import MAX_ERROR_CHARS
from romeo_mcp.guard import GuardError
from romeo_mcp.execution_backend import _error
from romeo_mcp.observability import ReadCache
from romeo_mcp.profiles import ProfiledServer
from romeo_mcp.ssh import Result

STATUS = ("###NODES\nn1|idle|x64cpu\nn1|idle|x64cpu\n###PART\nshort|up|1-00:00:00\n"
          "###SHARE\ntest-project|0|1\n###QUEUE\n")
SHARE = ("Account|User|RawShares|NormShares|RawUsage|EffectvUsage|FairShare|\n"
         "test-project||1|1|7200|0.5|1|\n"
         "test-project|test-user|1|1|3600|0.25|1|\n")
QUOTA = "gpfs home USR 1G 2G 3G 0 none 1 2 3 0 none\n"


class ErrorBudgets(unittest.TestCase):
    def test_domain_and_manually_returned_errors_are_bounded(self):
        huge = 'fictional_' * 131072
        result = _error(huge, plan_id='preserved')
        self.assertLessEqual(len(result['error']), MAX_ERROR_CHARS)
        self.assertTrue(result['error_truncated'])
        self.assertEqual(result['plan_id'], 'preserved')
        self.assertEqual(_error('small'), {'ok': False, 'error': 'small'})
        with patch.object(noyau, 'server', ProfiledServer(name='test')):
            @noyau.outil()
            def domain() -> dict[str, Any]:
                raise ValueError(huge)

            @noyau.outil()
            def unexpected() -> dict[str, Any]:
                raise RuntimeError(huge)

            @noyau.outil()
            def manual() -> dict[str, Any]:
                return {'ok': False, 'error': huge}
        for fn in (domain, unexpected, manual):
            result = fn()
            self.assertLessEqual(len(result['error']), MAX_ERROR_CHARS)
            self.assertLess(len(json.dumps(result)), 2000)

    def test_stdio_schema_and_domain_errors_remain_compact_and_recover(self):
        async def exercise():
            with tempfile.TemporaryDirectory() as temporary:
                env = {**os.environ, 'ROMEO_CONFIG': str(Path(temporary) / 'config.json'),
                       'ROMEO_MCP_DB': str(Path(temporary) / 'jobs.db'),
                       'ROMEO_UPDATES_DIR': str(Path(temporary) / 'updates'),
                       'ROMEO_REPORTS_DIR': str(Path(temporary) / 'reports'),
                       'ROMEO_UPDATE_CHECK': '0', 'ROMEO_HOME': '/home/user',
                       'ROMEO_SCRATCH': '/scratch/test-user', 'PYTHONIOENCODING': 'utf-8',
                       'PYTHONPATH': str(Path(__file__).resolve().parents[1])}
                parameters = StdioServerParameters(command=sys.executable,
                    args=['-m', 'romeo_mcp', 'serve'], env=env)
                async with stdio_client(parameters) as (read, write):
                    async with ClientSession(read, write) as client:
                        await client.initialize()
                        for count in (256, 4096, 32768):
                            result = await client.call_tool('job_pipeline_prepare',
                                {'name': 'fictional', 'stages': ['REJECTED_VALUE'] * count},
                                read_timeout_seconds=15)
                            self.assertTrue(result.is_error)
                            self.assertNotIn('REJECTED_VALUE', result.content[0].text)
                            self.assertIn(str(count), result.content[0].text)
                            self.assertLess(len(result.model_dump_json()), 4096)
                        for count in (65536, 1048576):
                            result = await client.call_tool('romeo_software', {'arch': 'x' * count},
                                                            read_timeout_seconds=15)
                            self.assertFalse(result.structured_content['ok'])
                            self.assertLess(len(result.model_dump_json()), 4096)
                        unknown = await client.call_tool('x' * 65536, {}, read_timeout_seconds=15)
                        self.assertTrue(unknown.is_error)
                        self.assertLess(len(unknown.model_dump_json()), 4096)
                        healthy = await client.call_tool('tool_profile_get', {}, read_timeout_seconds=5)
                        self.assertTrue(healthy.structured_content['ok'])
        asyncio.run(exercise())


class PrivacyBoundaries(unittest.TestCase):
    def test_large_identifiers_finish_within_a_bounded_child_process(self):
        code = ("from romeo_mcp.privacy import sensitive_path,redact_text; "
                "values=['x'*1048576,'x.'*32768,'x-'*32768]; "
                "assert all(not sensitive_path(v) and redact_text(v)==v for v in values)")
        result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
            cwd=str(Path(__file__).resolve().parents[1]), timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_nested_and_prefixed_secret_assignments_still_hide_values(self):
        for text in ("API_TOKEN=fictional_value", "--api-key fictional_value",
                     "payload='API_TOKEN=fictional_value'", "prefix-secret-suffix=fictional_value"):
            filtered = privacy.redact_text(text)
            self.assertNotIn('fictional_value', filtered)
            self.assertIn(privacy.REDACTED, filtered)

    def test_oversized_path_is_rejected_before_filtering_or_ssh(self):
        connection = SimpleNamespace(home='/home/user', scratch='/scratch/test-user', path_aliases=[])
        with patch.object(reproducibility, 'sensitive_path') as filtering:
            with self.assertRaises(GuardError):
                reproducibility.observe_files(connection, 'x' * 65536, [])
            filtering.assert_not_called()


class ContextObservations(unittest.TestCase):
    def setUp(self):
        self.connection = SimpleNamespace(host='offline-host', user='test-user',
            home='/home/user', scratch='/scratch/test-user', path_aliases=[])
        self.enterContext(patch.object(context, 'session', return_value=self.connection))
        self.enterContext(patch.object(jobs, 'session', return_value=self.connection))
        self.enterContext(patch.object(context, '_STATUS_CACHE', ReadCache()))

    def test_failed_or_truncated_modules_are_not_a_catalog(self):
        for rc, truncated in ((42, False), (0, True)):
            with patch.object(context, '_sh', return_value=Result(rc, 'python/3.13\n', 0, truncated)):
                self.assertFalse(context.romeo_modules()['ok'])
        with patch.object(context, '_sh', return_value=Result(0, '', 0)):
            self.assertEqual(context.romeo_modules()['count'], 0)

    def test_status_requires_sections_and_valid_rows_and_never_caches_invalid_data(self):
        invalid = ['', 'NOT_AN_OBSERVATION', STATUS.replace('###PART\n', ''),
                   STATUS.replace('n1|idle|x64cpu', 'broken'),
                   STATUS.replace('###SHARE\ntest-project|0|1', '###SHARE'),
                   STATUS.replace('###QUEUE\n', ''), STATUS + 'broken_queue_row\n',
                   STATUS + '###NODES\nn2|idle|x64cpu\n',
                   STATUS.replace('x64cpu', 'unknown_arch')]
        for text in invalid:
            with self.subTest(text=text), patch.object(context, '_sh', return_value=Result(0, text, 0)) as remote:
                self.assertFalse(context.romeo_status(max_age_seconds=5)['ok'])
                self.assertFalse(context.romeo_status(max_age_seconds=5)['ok'])
                self.assertEqual(remote.call_count, 2)

    def test_valid_status_can_have_an_empty_queue_and_is_cached_explicitly(self):
        with patch.object(context, '_sh', return_value=Result(0, STATUS, 0)) as remote:
            result = context.romeo_status()
            self.assertTrue(result['ok'], result)
            self.assertEqual(result['nodes']['x64cpu']['total'], 1)
            self.assertEqual(result['my_jobs'], [])
            self.assertTrue(result['observation']['current_state_observed'])
            cached = context.romeo_status(max_age_seconds=5)
            self.assertTrue(cached['observation']['cached'])
            self.assertFalse(cached['observation']['current_state_observed'])
            self.assertEqual(remote.call_count, 1)
        with patch.object(context, '_sh', return_value=Result(0, STATUS.split('###QUEUE')[0], 0)):
            self.assertTrue(context.romeo_status(include_queue=False)['ok'])

    def test_quota_refuses_failed_truncated_empty_and_malformed_outputs(self):
        for response in (Result(42, QUOTA, 0), Result(0, QUOTA, 0, True),
                         Result(0, '', 0), Result(0, 'unexpected', 0),
                         Result(0, 'gpfs home USR 1G', 0),
                         Result(0, 'gpfs home USR bad bad bad bad none', 0),
                         Result(0, 'gpfs home UNKNOWN 1G 2G 3G 0 none', 0)):
            with self.subTest(response=response), patch.object(context, '_sh', return_value=response):
                self.assertFalse(context.romeo_quota()['ok'])
        with patch.object(context, '_sh', return_value=Result(0, QUOTA, 0)):
            self.assertTrue(context.romeo_quota()['ok'])
            self.assertFalse(context.romeo_quota(project='fictional')['ok'])
        with patch.object(context, '_sh', return_value=Result(0, QUOTA + QUOTA.replace('USR', 'GRP'), 0)):
            self.assertTrue(context.romeo_quota(project='fictional')['ok'])

    def test_forecast_refuses_failed_truncated_malformed_and_absent_account(self):
        for response in (Result(42, SHARE, 0), Result(0, SHARE, 0, True),
                         Result(0, '', 0), Result(0, STATUS, 0),
                         Result(0, SHARE.replace('test-project', 'other-account'), 0),
                         Result(0, SHARE.replace('7200|0.5', 'bad|bad'), 0),
                         Result(0, SHARE.replace('7200|0.5', 'nan|inf'), 0)):
            with self.subTest(response=response), patch.object(jobs, '_sh', return_value=response):
                self.assertFalse(jobs.romeo_fairshare_forecast()['ok'])

    def test_forecast_preserves_normal_and_zero_usage(self):
        with patch.object(jobs, '_sh', return_value=Result(0, SHARE, 0)):
            result = jobs.romeo_fairshare_forecast(2, 1, 1)
            self.assertTrue(result['ok'], result)
            self.assertEqual(result['charge_simulee']['cout_coeur_secondes'], 7200)
            self.assertEqual(result['hausse_relative_pct'], 100)
            self.assertEqual(result['usage_effectif_projete'], 1)
        with patch.object(jobs, '_sh', return_value=Result(0, SHARE.replace('7200|0.5', '0|0'), 0)):
            result = jobs.romeo_fairshare_forecast(2, 0, 1)
            self.assertTrue(result['ok'], result)
            self.assertIsNone(result['hausse_relative_pct'])

    def test_slot_refuses_failed_or_truncated_pending_even_with_good_status(self):
        with patch.object(jobs, 'romeo_status', return_value={'ok': True, 'nodes': {}}):
            for response in (Result(42, 'short|1', 0), Result(0, 'short|1', 0, True),
                             Result(0, 'malformed', 0), Result(0, 'short|bad', 0)):
                with patch.object(jobs, '_sh', return_value=response):
                    self.assertFalse(jobs.suggest_submission_slot()['ok'])
            with patch.object(jobs, '_sh', return_value=Result(0, '', 0)):
                self.assertTrue(jobs.suggest_submission_slot()['ok'])

    def test_extreme_numerics_are_domain_errors_before_any_ssh(self):
        with patch.object(jobs, 'session') as connection, patch.object(jobs, '_sh') as remote, \
                patch.object(jobs, 'romeo_status') as status:
            for hours in (1e308, float('nan'), float('inf'), -float('inf')):
                for function, args in ((jobs.suggest_submission_slot, {'hours': hours}),
                                       (jobs.romeo_fairshare_forecast, {'duration_hours': hours})):
                    result = function(**args)
                    self.assertFalse(result['ok'])
                    self.assertNotIn('inattendu', result)
            for args in ({'simulated_cpus': 10**400}, {'simulated_gpus': 10**400},
                         {'simulated_cpus': 10**308, 'duration_hours': 1}):
                result = jobs.romeo_fairshare_forecast(**args)
                self.assertFalse(result['ok'])
                self.assertNotIn('inattendu', result)
            connection.assert_not_called()
            remote.assert_not_called()
            status.assert_not_called()


if __name__ == '__main__':
    unittest.main()
