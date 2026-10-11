"""Context reads stay responsive under real SDK/stdio mutation pressure; no network/jobs."""
from __future__ import annotations

import asyncio
from collections import Counter
from contextlib import ExitStack, nullcontext
from contextvars import ContextVar
import inspect
import json
import os
from pathlib import Path
import shlex
import socket
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from typing import Annotated, Any
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SELF = Path(__file__).resolve()
sys.path.insert(0, str(ROOT))

CHILD = len(sys.argv) == 3 and sys.argv[1] == '--stdio-fixture'
if not CHILD:
    import offline  # noqa: F401 - existing offline-suite isolation


def isolated_environment(root: Path) -> dict[str, str]:
    temporary = root / 'temporary'
    temporary.mkdir(parents=True, exist_ok=True)
    return {'ROMEO_CONFIG': str(root / 'config.json'), 'ROMEO_MCP_DB': str(root / 'jobs.db'),
            'ROMEO_CONCURRENCY_ROOT': str(root / 'concurrency'),
            'ROMEO_REPORTS_DIR': str(root / 'issue-reports'), 'ROMEO_UPDATES_DIR': str(root / 'updates'),
            'ROMEO_UPDATE_CHECK': '0', 'ROMEO_AUTO_UPDATE': '0', 'ROMEO_AUTO_ISSUES': '0',
            'ROMEO_TOOL_PROFILE': 'expert', 'ROMEO_HOST': 'invalid-offline-host',
            'ROMEO_ACCOUNT': 'test-project', 'ROMEO_QOS': 'normal',
            'TEMP': str(temporary), 'TMP': str(temporary),
            'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONIOENCODING': 'utf-8'}


if CHILD:
    child_root = Path(sys.argv[2]).resolve()
    if not child_root.is_dir():
        raise ValueError('Existing isolated fixture directory required')
    os.environ.update(isolated_environment(child_root))
    sys.dont_write_bytecode = True

import anyio.to_thread
from mcp import ClientSession, StdioServerParameters, stdio_client
from mcp.server.mcpserver import Context
from mcp.types import ToolAnnotations
from pydantic import Field
from romeo_mcp import server as assembled, ssh, files
from romeo_mcp import outils_donnees as data_tools, outils_accompagnement as discovery
from romeo_mcp import outils_diagnostics as diagnostics
from romeo_mcp.noyau import READ_ONLY, MUTATING
from romeo_mcp.observability import Measurements
from romeo_mcp.profiles import ProfiledServer
from romeo_mcp.remote_reads import READ_TEXT, LIST_DIRECTORY
from romeo_mcp.resource_locks import ResourceLease


def result_data(result) -> dict:
    structured = getattr(result, 'structured_content', None)
    if structured is not None:
        return structured
    content = getattr(result, 'content', result[0] if isinstance(result, tuple) else result)
    for item in content:
        if getattr(item, 'type', '') == 'text':
            return json.loads(item.text)
    raise AssertionError('Structured tool response expected')


async def eventually(predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError('Isolated worker/readiness deadline')
        await asyncio.sleep(.005)


def deny_network_guards(stack: ExitStack, permitted_root: Path | None = None):
    """Deny real transports even if a mock is accidentally missed."""
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_popen = subprocess.Popen

    def connect(connection, address):
        # Windows asyncio's internal socket pair is loopback-only.
        if isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1'):
            return original_connect(connection, address)
        raise AssertionError('Offline context suite forbids external network')

    def connect_ex(connection, address):
        if isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1'):
            return original_connect_ex(connection, address)
        raise AssertionError('Offline context suite forbids external network')

    def popen(argv, *args, **kwargs):
        if permitted_root is None or not isinstance(argv, (list, tuple)) or len(argv) != 4:
            raise AssertionError('Only the owned stdio fixture may start a subprocess')
        if (Path(str(argv[0])).resolve() != Path(sys.executable).resolve()
                or Path(str(argv[1])).resolve() != SELF or argv[2] != '--stdio-fixture'
                or not Path(str(argv[3])).resolve().is_relative_to(permitted_root)):
            raise AssertionError('External process/cluster command forbidden')
        return original_popen(argv, *args, **kwargs)

    stack.enter_context(patch.object(socket.socket, 'connect', connect))
    stack.enter_context(patch.object(socket.socket, 'connect_ex', connect_ex))
    stack.enter_context(patch.object(socket.socket, 'sendto', side_effect=AssertionError('UDP forbidden')))
    stack.enter_context(patch.object(socket, 'getaddrinfo', side_effect=AssertionError('DNS forbidden')))
    stack.enter_context(patch.object(subprocess, 'Popen', popen))
    stack.enter_context(patch.object(os, 'system', side_effect=AssertionError('Shell forbidden')))
    stack.enter_context(patch.object(ssh.RomeoSession, '_spawn', side_effect=AssertionError('Real SSH forbidden')))


class BlockedCalls:
    def __init__(self, root: Path):
        self.root = root
        self.release = threading.Event()
        self.lock = threading.Lock()
        self.entered = Counter()
        self.finished = Counter()

    def hold(self, kind: str):
        with self.lock:
            self.entered[kind] += 1
        deadline = time.monotonic() + 15
        while not self.release.is_set() and not (self.root / 'release').exists():
            if time.monotonic() >= deadline:
                raise AssertionError('Blocked fixture effect deadline')
            time.sleep(.005)
        with self.lock:
            self.finished[kind] += 1

    def snapshot(self) -> dict:
        with self.lock:
            return {'entered': dict(self.entered), 'finished': dict(self.finished)}


class FakeSession:
    host = 'invalid-offline-host'
    user = 'fixture'
    home = '/home/test'
    scratch = '/scratch_p/fixture'
    path_aliases = []
    home_aliases = []
    scratch_aliases = []
    connections = 0

    def __init__(self):
        self.timings = Measurements()

    def run(self, command, **kwargs):
        words = shlex.split(command)
        if words[:2] != ['python3', '-c']:
            raise AssertionError('Only declared read helper commands are simulated')
        if words[2] == READ_TEXT:
            payload = {'content': 'fixture context\n', 'total_lines': 1, 'truncated': False}
        elif words[2] == LIST_DIRECTORY:
            payload = {'entries': [{'name': 'context.txt', 'size': 16, 'type': 'file'}], 'truncated': False}
        else:
            raise AssertionError('Unknown helper; no real command execution')
        return ssh.Result(0, json.dumps(payload), 0)

    read = run


CONTEXT_READS = [('read_doc', {'page': 'index.md', 'max_chars': 500}),
                 ('search_docs', {'query': 'stockage', 'max_results': 1, 'max_chars': 500}),
                 ('romeo_capabilities', {'task': 'files'}), ('mcp_diagnostics', {}),
                 ('read_remote_file', {'path': '/scratch_p/fixture/context.txt', 'max_chars': 500}),
                 ('list_dir', {'path': '/scratch_p/fixture', 'limit': 1})]
CONTEXT_PRESSURES = (32, 40, 48, 64)


def install_real_context_tools(server: ProfiledServer, root: Path, blocked: BlockedCalls, stack: ExitStack):
    """Real public wrappers/schemas; only file effects and transport are fictional."""
    for name, _ in CONTEXT_READS:
        server.add_tool(getattr(assembled, name), annotations=READ_ONLY, structured_output=True)
    for name in ('tool_profile_get', 'tool_profile_set'):
        server.add_tool(getattr(assembled, name), annotations=READ_ONLY if name.endswith('_get') else MUTATING,
                        structured_output=True)
    for name in ('file_create', 'upload_to_romeo', 'download_from_romeo'):
        server.add_tool(getattr(assembled, name), annotations=MUTATING, structured_output=True)
    stack.enter_context(patch.object(discovery, 'server', server))
    stack.enter_context(patch.object(diagnostics, 'server', server))
    stack.enter_context(patch.object(data_tools, 'session', return_value=FakeSession()))
    # Path leases have independent tests. Simulate them here to isolate the
    # scheduling contract and prevent bookkeeping contention from ending a holder.
    stack.enter_context(patch.object(data_tools, 'ResourceLease', side_effect=lambda *a, **k: nullcontext()))

    def create(connection, target, content):
        blocked.hold('write')
        return {'ok': True, 'path': target, 'simulated': True}

    def upload(host, source, target):
        blocked.hold('write')
        return {'from': source, 'to': target, 'method': 'SIMULATED'}

    def download(host, source, target, recursive=False):
        blocked.hold('write')
        return {'from': source, 'to': target, 'method': 'SIMULATED'}

    stack.enter_context(patch.object(data_tools, 'create_file', side_effect=create))
    stack.enter_context(patch.object(files, 'upload', side_effect=upload))
    stack.enter_context(patch.object(files, 'download', side_effect=download))
    (root / 'source.bin').write_bytes(b'owned fixture source')


def mutation_request(root: Path, number: int):
    if number % 3 == 0:
        return 'file_create', {'path': '/scratch_p/fixture/file-' + str(number), 'content': 'fixture'}
    if number % 3 == 1:
        return 'upload_to_romeo', {'local_path': str(root / 'source.bin'),
                                 'remote_path': '/scratch_p/fixture/file-' + str(number), 'verify': False}
    return 'download_from_romeo', {'remote_path': '/scratch_p/fixture/file-' + str(number),
                                 'local_path': str(root / ('download-' + str(number))), 'verify': False}


class ContextConcurrency(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='romeo-context-reserve-')
        self.root = Path(self.temporary.name).resolve()
        self.last_stats = {}
        self.addCleanup(self.temporary.cleanup)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ, isolated_environment(self.root)))
        deny_network_guards(self.stack, self.root)

    def assert_refused(self, response):
        value = result_data(response)
        self.assertTrue(value.get('busy'), value)
        self.assertFalse(value.get('execution_started'), value)
        self.assertFalse(value['ok'], value)

    async def test_reserved_admission_and_distinct_worker_limits(self):
        server = ProfiledServer(name='isolated-context-pressure')
        blocked = BlockedCalls(self.root)

        def writing(number: int) -> dict[str, Any]:
            blocked.hold('write')
            return {'ok': True, 'number': number}

        def reading(number: int) -> dict[str, Any]:
            blocked.hold('read')
            return {'ok': True, 'number': number}

        server.add_tool(writing, annotations=MUTATING, structured_output=True)
        server.add_tool(reading, annotations=READ_ONLY, structured_output=True)
        writes = [asyncio.create_task(server.call_tool('writing', {'number': n})) for n in range(80)]
        reads = []
        try:
            await eventually(lambda: blocked.snapshot()['entered'].get('write') == 32)
            await asyncio.sleep(.02)
            self.assertEqual(server._active_calls, 48)
            self.assertEqual(sum(task.done() for task in writes), 32)
            for task in writes:
                if task.done():
                    self.assert_refused(task.result())
            reads = [asyncio.create_task(server.call_tool('reading', {'number': n})) for n in range(16)]
            await eventually(lambda: blocked.snapshot()['entered'].get('read') == 16)
            self.assertEqual(server._active_calls, 64)
            # SDK/stdio's default limiter is not borrowed by either tool lane.
            default = anyio.to_thread.current_default_thread_limiter()
            self.assertEqual(default.total_tokens, 40)
            self.assertEqual(default.borrowed_tokens, 0)
            overflow = await asyncio.gather(*[server.call_tool('writing', {'number': 1000 + n}) for n in range(64)],
                                           *[server.call_tool('reading', {'number': 1000 + n}) for n in range(64)])
            for response in overflow:
                self.assert_refused(response)
            self.assertEqual(blocked.snapshot()['entered'], {'write': 32, 'read': 16})
            self.assertEqual(len(await asyncio.wait_for(server.list_tools(), 2)), 2)
        finally:
            blocked.release.set()
            await asyncio.gather(*writes, *reads, return_exceptions=True)
            await eventually(lambda: server._active_calls == 0)
        self.assertEqual(blocked.snapshot()['finished'], {'write': 48, 'read': 16})

    async def test_unknown_and_unannotated_tools_use_mutation_admission(self):
        server = ProfiledServer(name='isolated-default-classification')
        blocked = BlockedCalls(self.root)
        plain_calls = []

        def holder() -> dict[str, Any]:
            blocked.hold('write')
            return {'ok': True}

        def unannotated() -> dict[str, Any]:
            plain_calls.append(True)
            return {'ok': True}

        def trusted_read() -> dict[str, Any]:
            return {'ok': True}

        server.add_tool(holder, annotations=MUTATING, structured_output=True)
        server.add_tool(unannotated, structured_output=True)
        server.add_tool(trusted_read, annotations=ToolAnnotations(read_only_hint=True), structured_output=True)
        holders = [asyncio.create_task(server.call_tool('holder', {})) for _ in range(48)]
        try:
            await eventually(lambda: blocked.snapshot()['entered'].get('write') == 32)
            self.assert_refused(await server.call_tool('unannotated', {'readOnlyHint': True}))
            self.assert_refused(await server.call_tool('unknown-tool', {'readOnlyHint': True}))
            self.assertEqual(plain_calls, [])
            self.assertTrue(result_data(await asyncio.wait_for(server.call_tool('trusted_read', {}), 2))['ok'])
        finally:
            blocked.release.set()
            await asyncio.gather(*holders, return_exceptions=True)
            await eventually(lambda: server._active_calls == 0)
        self.assertTrue(result_data(await server.call_tool('unannotated', {}))['ok'])
        self.assertEqual(plain_calls, [True])

    async def test_cancelled_sync_calls_keep_their_lane_until_effect_finishes(self):
        for kind, count, annotation in (('write', 48, MUTATING), ('read', 16, READ_ONLY)):
            with self.subTest(lane=kind):
                server = ProfiledServer(name='isolated-cancel-' + kind)
                blocked = BlockedCalls(self.root)

                def controlled(number: int) -> dict[str, Any]:
                    blocked.hold(kind)
                    return {'ok': True, 'number': number}

                server.add_tool(controlled, annotations=annotation, structured_output=True)
                requests = [asyncio.create_task(server.call_tool('controlled', {'number': n})) for n in range(count)]
                try:
                    await eventually(lambda: blocked.snapshot()['entered'].get(kind) == min(count, 32))
                    requests[0].cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await requests[0]
                    self.assertEqual(server._active_calls, count)
                    self.assert_refused(await server.call_tool('controlled', {'number': 999}))
                finally:
                    blocked.release.set()
                    await asyncio.gather(*requests, return_exceptions=True)
                    await eventually(lambda: server._active_calls == 0)
                self.assertEqual(blocked.snapshot()['finished'][kind], count)
                self.assertTrue(result_data(await server.call_tool('controlled', {'number': -1}))['ok'])

    async def test_sync_dispatch_preserves_signature_context_schema_and_resource_ownership(self):
        server = ProfiledServer(name='isolated-context-propagation')
        marker = ContextVar('test_request_context', default='unset')
        caller_thread = threading.get_ident()
        supplied_context = SimpleNamespace(request_id='fictional-request')
        target = self.root / 'same-resource'
        calls = []

        def compatible(value: Annotated[int, Field(strict=True)], *, suffix: str = 'default',
                       ctx: Context | None = None) -> dict[str, Any]:
            calls.append(value)
            with ResourceLease([(target, True)]):
                return {'ok': True, 'value': value, 'suffix': suffix, 'marker': marker.get(),
                        'worker_thread': threading.get_ident() != caller_thread,
                        'same_context': ctx is supplied_context}

        original_signature = inspect.signature(compatible)
        server.add_tool(compatible, annotations=READ_ONLY, structured_output=True)
        manager = server._tool_manager.get_tool('compatible')
        self.assertEqual(inspect.signature(manager.fn), original_signature)
        schema = (await server.list_tools())[0].input_schema
        self.assertEqual(schema['required'], ['value'])
        self.assertEqual(set(schema['properties']), {'value', 'suffix'})
        marker_token = marker.set('caller-context')
        try:
            with ResourceLease([(target, True)]):
                value = result_data(await server.call_tool('compatible', {'value': 7}, context=supplied_context))
            self.assertTrue(value['ok'], value)
            self.assertTrue(value['worker_thread'], value)
            self.assertTrue(value['same_context'], value)
            self.assertEqual(value['marker'], 'caller-context')
            self.assertEqual(value['suffix'], 'default')
            invalid = await server.call_tool('compatible', {'value': True})
            self.assertTrue(getattr(invalid, 'is_error', False))
            self.assertEqual(calls, [7])
            self.assertEqual(marker.get(), 'caller-context')
        finally:
            marker.reset(marker_token)

    async def test_native_async_handler_stays_on_event_loop_without_double_dispatch(self):
        server = ProfiledServer(name='isolated-native-async')
        caller_thread = threading.get_ident()
        marker = ContextVar('native_async_marker', default='unset')
        calls = []

        async def native(value: int) -> dict[str, Any]:
            calls.append(value)
            await asyncio.sleep(0)
            return {'ok': True, 'thread': threading.get_ident(), 'marker': marker.get()}

        server.add_tool(native, annotations=READ_ONLY, structured_output=True)
        token = marker.set('native-context')
        try:
            response = result_data(await server.call_tool('native', {'value': 3}))
        finally:
            marker.reset(token)
        self.assertEqual(response['thread'], caller_thread)
        self.assertEqual(response['marker'], 'native-context')
        self.assertEqual(calls, [3])
        self.assertEqual(anyio.to_thread.current_default_thread_limiter().borrowed_tokens, 0)

    async def test_six_real_context_handlers_available_with_32_40_48_mutations(self):
        for pressure in CONTEXT_PRESSURES:
            with self.subTest(mutations=pressure), ExitStack() as local:
                server = ProfiledServer(name='isolated-real-context-' + str(pressure))
                blocked = BlockedCalls(self.root)
                install_real_context_tools(server, self.root, blocked, local)
                requests = [asyncio.create_task(server.call_tool(*mutation_request(self.root, n))) for n in range(pressure)]
                try:
                    await eventually(lambda: blocked.snapshot()['entered'].get('write') == 32)
                    replies = await asyncio.wait_for(asyncio.gather(*[server.call_tool(name, args) for name, args in CONTEXT_READS]), 2)
                    self.assertTrue(all(result_data(r).get('ok') for r in replies), [result_data(r) for r in replies])
                    self.assertEqual(blocked.snapshot()['finished'], {})
                    self.assertTrue(result_data(await asyncio.wait_for(server.call_tool('tool_profile_get', {}), 2))['ok'])
                    names = {tool.name for tool in await asyncio.wait_for(server.list_tools(), 2)}
                    self.assertEqual(names, {name for name, _ in CONTEXT_READS} | {'tool_profile_get', 'tool_profile_set', 'file_create', 'upload_to_romeo', 'download_from_romeo'})
                finally:
                    blocked.release.set()
                    await asyncio.gather(*requests, return_exceptions=True)
                    await eventually(lambda: server._active_calls == 0)
                self.assertEqual(blocked.snapshot()['finished'].get('write'), min(48, pressure))
                self.assertEqual(sum(bool(result_data(r.result()).get('busy')) for r in requests), max(0, pressure - 48))
                self.assertTrue(all(result_data(r.result()).get('ok') or result_data(r.result()).get('busy') for r in requests))

    async def stdio_fixture(self, root):
        parameters = StdioServerParameters(command=sys.executable,
            args=[str(SELF), '--stdio-fixture', str(root)], env={**os.environ, **isolated_environment(root)})
        return parameters

    def read_stats(self, root):
        try:
            value = json.loads((root / 'stats.json').read_text(encoding='utf-8'))
            self.last_stats[root] = value
            return value
        except (FileNotFoundError, PermissionError, ValueError):
            # Windows can transiently deny a reader while the monitor replaces
            # its file. Readiness still waits for fresh counters; a publication
            # race must not turn an already-observed snapshot into missing data.
            return self.last_stats.get(root, {})

    async def test_stdio_context_handlers_profile_and_catalogue_available(self):
        for pressure in CONTEXT_PRESSURES:
            with self.subTest(mutations=pressure):
                root = self.root / ('stdio-' + str(pressure))
                root.mkdir()
                parameters = await self.stdio_fixture(root)
                async with stdio_client(parameters) as (read, write), ClientSession(read, write) as client:
                    await client.initialize()
                    requests = [asyncio.create_task(client.call_tool(*mutation_request(root, n))) for n in range(pressure)]
                    pending = []
                    catalogue = None
                    try:
                        await eventually(lambda: self.read_stats(root).get('entered', {}).get('write') == 32
                                         and self.read_stats(root).get('active') == min(pressure, 48)
                                         and sum(t.done() for t in requests) == max(0, pressure - 48))
                        pending = [asyncio.create_task(client.call_tool(name, args)) for name, args in CONTEXT_READS]
                        pending.append(asyncio.create_task(client.call_tool('tool_profile_get', {})))
                        catalogue = asyncio.create_task(client.list_tools())
                        replies = await asyncio.wait_for(asyncio.gather(*pending, catalogue), 2)
                        self.assertTrue(all(result_data(r).get('ok') for r in replies[:-1]), replies)
                        self.assertTrue(any(t.name == 'read_doc' for t in replies[-1].tools))
                        self.assertEqual(self.read_stats(root).get('finished'), {})
                        self.assertEqual(self.read_stats(root).get('default_tokens'), 40)
                    finally:
                        (root / 'release').write_text('release', encoding='utf-8')
                        await asyncio.gather(*requests, *pending, *([catalogue] if catalogue else []), return_exceptions=True)
                    self.assertEqual(sum(bool(result_data(r.result()).get('busy')) for r in requests), max(0, pressure - 48))
                    self.assertTrue(all(result_data(r.result()).get('ok') or result_data(r.result()).get('busy') for r in requests))
                    await eventually(lambda: self.read_stats(root).get('active') == 0)

    async def test_file_mutations_use_long_session_context_reads_use_short_session(self):
        server = ProfiledServer(name='isolated-ssh-session-selection')
        session_choices = []

        def choose_session(*args, **kwargs):
            session_choices.append(kwargs.get('longue', False))
            return FakeSession()

        with ExitStack() as local:
            local.enter_context(patch.object(data_tools, 'session', side_effect=choose_session))
            local.enter_context(patch.object(data_tools, 'ResourceLease', side_effect=lambda *a, **k: nullcontext()))
            local.enter_context(patch.object(data_tools, 'create_file', return_value={'ok': True}))
            local.enter_context(patch.object(data_tools, 'replace_file', return_value={'ok': True}))
            for name in ('file_create', 'file_replace', 'read_remote_file', 'list_dir'):
                server.add_tool(getattr(assembled, name), annotations=READ_ONLY if name in ('read_remote_file', 'list_dir') else MUTATING,
                                structured_output=True)
            requests = [('file_create', {'path': '/scratch_p/fixture/context.txt', 'content': 'fixture'}),
                        ('file_replace', {'path': '/scratch_p/fixture/context.txt', 'content': 'fixture'}),
                        *CONTEXT_READS[-2:]]
            for name, args in requests:
                self.assertTrue(result_data(await server.call_tool(name, args))['ok'])
            self.assertEqual(session_choices, [True, True, False, False])

    async def test_offline_guards_block_network_shell_and_unowned_processes(self):
        with socket.socket() as connection:
            with self.assertRaisesRegex(AssertionError, 'forbids external network'):
                connection.connect(('203.0.113.1', 9))
            with self.assertRaisesRegex(AssertionError, 'forbids external network'):
                connection.connect_ex(('203.0.113.1', 9))
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
            with self.assertRaisesRegex(AssertionError, 'UDP forbidden'):
                connection.sendto(b'fixture', ('203.0.113.1', 9))
        with self.assertRaisesRegex(AssertionError, 'DNS forbidden'):
            socket.getaddrinfo('invalid-offline-host', 22)
        with self.assertRaisesRegex(AssertionError, 'stdio fixture'):
            subprocess.Popen(['ssh', 'invalid-offline-host', 'true'])
        with self.assertRaisesRegex(AssertionError, 'Shell forbidden'):
            os.system('echo never executed')

    async def test_real_stdio_rpc_cancellation_preserves_both_full_lanes(self):
        root = self.root / 'stdio-cancel'
        root.mkdir()
        parameters = await self.stdio_fixture(root)
        async with stdio_client(parameters) as (read, write), ClientSession(read, write) as client:
            await client.initialize()
            writes = [asyncio.create_task(client.call_tool(*mutation_request(root, n))) for n in range(48)]
            reads = []
            try:
                await eventually(lambda: self.read_stats(root).get('entered', {}).get('write') == 32
                                 and self.read_stats(root).get('active') == 48)
                reads = [asyncio.create_task(client.call_tool('blocked_read', {'number': n})) for n in range(16)]
                await eventually(lambda: self.read_stats(root).get('entered', {}).get('read') == 16
                                 and self.read_stats(root).get('active') == 64)
                writes[0].cancel()
                reads[0].cancel()
                await asyncio.gather(writes[0], reads[0], return_exceptions=True)
                self.assert_refused(await asyncio.wait_for(client.call_tool('file_create', {'path': '/scratch_p/fixture/overflow', 'content': 'fixture'}), 2))
                self.assert_refused(await asyncio.wait_for(client.call_tool('blocked_read', {'number': 99}), 2))
                self.assertEqual(self.read_stats(root).get('active'), 64)
                self.assertTrue((await asyncio.wait_for(client.list_tools(), 2)).tools)
            finally:
                (root / 'release').write_text('release', encoding='utf-8')
                await asyncio.gather(*writes, *reads, return_exceptions=True)
            await eventually(lambda: self.read_stats(root).get('active') == 0
                             and self.read_stats(root).get('finished') == {'write': 48, 'read': 16})


async def run_stdio_fixture():
    root = child_root
    blocked = BlockedCalls(root)
    server = ProfiledServer(name='isolated-context-stdio')
    with ExitStack() as stack:
        deny_network_guards(stack)
        install_real_context_tools(server, root, blocked, stack)

        def blocked_read(number: int) -> dict[str, Any]:
            blocked.hold('read')
            return {'ok': True, 'number': number}

        server.add_tool(blocked_read, annotations=READ_ONLY, structured_output=True)

        async def monitor():
            while True:
                value = {**blocked.snapshot(), 'active': server._active_calls,
                         'default_tokens': anyio.to_thread.current_default_thread_limiter().total_tokens}
                temporary = root / 'stats.tmp'
                temporary.write_text(json.dumps(value), encoding='utf-8')
                for attempt in range(6):
                    try:
                        os.replace(temporary, root / 'stats.json')
                        break
                    except PermissionError:
                        if attempt == 5:
                            raise
                        await asyncio.sleep(.01)
                await asyncio.sleep(.01)

        watch = asyncio.create_task(monitor())
        try:
            await server.run_stdio_async()
        finally:
            blocked.release.set()
            watch.cancel()
            await asyncio.gather(watch, return_exceptions=True)


if __name__ == '__main__':
    if CHILD:
        asyncio.run(run_stdio_fixture())
    else:
        unittest.main()
