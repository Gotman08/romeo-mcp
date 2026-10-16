"""Selection des outils annonces au client, avec acces au catalogue complet."""

from mcp.server import MCPServer, NotificationOptions
from mcp.server.stdio import stdio_server
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.utilities.func_metadata import FuncMetadata
from mcp.types import CallToolResult, TextContent
from pydantic import ValidationError
import json
import threading
import asyncio
import functools
import anyio

from .config import setting
from .errors import bounded_message


class _BoundedArguments(FuncMetadata):
    """Intercepte la validation avant que le SDK formate chaque valeur rejetee."""

    def validate_arguments(self, arguments_to_validate):
        try:
            return super().validate_arguments(arguments_to_validate)
        except ValidationError as exc:
            # errors() et str(exc) materialisent toutes les erreurs et leurs
            # entrees. Le compteur suffit ; le schema reste dans tools/list.
            message = ValueError(
                "{} erreur(s) d'arguments ; relire le schema de l'outil dans tools/list."
                .format(exc.error_count()))
            raise ValidationError.from_exception_data("Arguments", [{
                "type": "value_error", "loc": (), "input": None,
                "ctx": {"error": message},
            }]) from None


PROFILES = ("essential", "full", "expert")
EXPERT_TOOLS = frozenset({"compute_command_prepare", "compute_command_run", "login_command_run"})
ESSENTIAL_TOOLS = frozenset({
    "mcp_issue_policy_get", "mcp_issue_policy_set", "mcp_issue_report", "mcp_issue_publish", "mcp_issue_status",
    "mcp_update_check", "mcp_update_start", "mcp_update_status", "mcp_update_rollback", "mcp_update_policy",
    "tool_profile_get", "tool_profile_set", "search_docs", "read_doc", "romeo_status", "romeo_quota",
    "romeo_software", "job_prepare", "job_submit", "job_status", "job_log_tail", "job_log_search", "list_jobs",
    "cancel_job", "diagnose_job", "job_efficiency", "list_dir",
    "upload_to_romeo", "download_from_romeo", "job_report_collect", "job_report_export", "plan_get",
    "mcp_diagnostics", "romeo_capabilities", "job_observation_get",
    "job_resume_prepare", "job_resume_submit", "job_resume_status", "checkpoint_inspect", "job_checkpoint_request",
    "romeollm_catalog", "romeollm_status", "romeollm_launch_prepare", "romeollm_launch",
    "romeollm_logs", "romeollm_endpoint", "romeollm_stop", "romeollm_gateway_status",
    "romeollm_gateway_start", "romeollm_gateway_stop", "romeollm_chat",
})


def validate_profile(value: str) -> str:
    if value not in PROFILES:
        raise ValueError("Profil d'outils inconnu : choisir essential, full ou expert.")
    return value


class ProfiledServer(MCPServer):
    """Le profil limite la decouverte, pas les droits d'execution."""

    def __init__(self, **kwargs):
        self.tool_profile = validate_profile(setting("ROMEO_TOOL_PROFILE", "full"))
        self._calls_lock = threading.Lock()
        self._profile_change = threading.Lock()
        self._active_calls = 0
        self._active_read_calls = 0
        self._active_mutating_calls = 0
        self._running_calls = set()
        self.max_active_calls = 64
        self.reserved_read_calls = 16
        # The SDK's default thread pool also serves stdin/stdout. Tool bodies
        # use their own limiters so a blocked backend cannot starve transport.
        self._read_workers = anyio.CapacityLimiter(16)
        self._mutation_workers = anyio.CapacityLimiter(32)
        super().__init__(**kwargs)

    def add_tool(self, fn, *args, **kwargs):
        super().add_tool(fn, *args, **kwargs)
        name = kwargs.get("name") or (args[0] if args else None) or fn.__name__
        tool = self._tool_manager.get_tool(name)
        metadata = tool.fn_metadata
        tool.fn_metadata = _BoundedArguments(
            arg_model=metadata.arg_model, output_schema=metadata.output_schema,
            output_model=metadata.output_model, wrap_output=metadata.wrap_output)
        if not tool.is_async:
            original = tool.fn
            limiter = self._read_workers if self._is_read_only(tool) else self._mutation_workers

            @functools.wraps(original)
            async def dispatched(*call_args, **call_kwargs):
                return await anyio.to_thread.run_sync(
                    functools.partial(original, *call_args, **call_kwargs), limiter=limiter)

            # Registration above keeps the original schema, argument validation,
            # output conversion and SDK context injection. Only dispatch changes.
            tool.fn = dispatched
            tool.is_async = True

    @staticmethod
    def _is_read_only(tool):
        return (tool is not None and tool.annotations is not None
                and tool.annotations.model_dump(by_alias=True).get("readOnlyHint") is True)

    async def call_tool(self, name, arguments, context=None):
        read_only = self._is_read_only(self._tool_manager.get_tool(name))
        with self._calls_lock:
            # Small limits used by embedders/tests still allow a first mutation.
            reserved = min(self.reserved_read_calls, max(0, self.max_active_calls - 1))
            lane_full = (self._active_read_calls >= min(self.reserved_read_calls, self.max_active_calls)
                         if read_only else self._active_mutating_calls >= self.max_active_calls - reserved)
            if self._active_calls >= self.max_active_calls or lane_full:
                message = {'ok': False, 'busy': True, 'execution_started': False,
                           'error': 'Trop d\'appels simultanes ; attends la fin des operations en cours.'}
                return CallToolResult(content=[TextContent(type='text', text=json.dumps(message))], is_error=True)
            self._active_calls += 1
            if read_only:
                self._active_read_calls += 1
            else:
                self._active_mutating_calls += 1
        task = asyncio.create_task(self._execute_tool(name, arguments, context, read_only))
        self._running_calls.add(task)
        def finished(completed):
            self._running_calls.discard(completed)
            if not completed.cancelled():
                completed.exception()
        task.add_done_callback(finished)
        # A cancelled RPC does not make a still-running synchronous operation
        # disappear from admission accounting or permit an unsafe replay.
        return await asyncio.shield(task)

    async def _execute_tool(self, name, arguments, context, read_only):
        # Borne aussi le nom d'un outil inconnu et les autres ToolError du SDK.
        try:
            return await super().call_tool(name, arguments, context)
        except ToolError as exc:
            return CallToolResult(content=[TextContent(type="text", text=bounded_message(str(exc)))],
                                  is_error=True)
        finally:
            with self._calls_lock:
                self._active_calls -= 1
                if read_only:
                    self._active_read_calls -= 1
                else:
                    self._active_mutating_calls -= 1

    async def list_tools(self):
        tools = await super().list_tools()
        if self.tool_profile == "essential":
            return [tool for tool in tools if tool.name in ESSENTIAL_TOOLS]
        if self.tool_profile == "full":
            return [tool for tool in tools if tool.name not in EXPERT_TOOLS]
        return tools

    async def run_stdio_async(self) -> None:
        # Le SDK 2.x n'annonce pas listChanged par defaut. Le transport reste
        # celui du SDK ; seul ce drapeau de capacite differe.
        async with stdio_server() as (read_stream, write_stream):
            await self._lowlevel_server.run(
                read_stream, write_stream,
                self._lowlevel_server.create_initialization_options(
                    notification_options=NotificationOptions(tools_changed=True)),
            )
