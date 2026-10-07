"""Selection des outils annonces au client, avec acces au catalogue complet."""

from mcp.server import MCPServer, NotificationOptions
from mcp.server.stdio import stdio_server

from .config import setting


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
})


def validate_profile(value: str) -> str:
    if value not in PROFILES:
        raise ValueError("Profil d'outils inconnu : choisir essential, full ou expert.")
    return value


class ProfiledServer(MCPServer):
    """Le profil limite la decouverte, pas les droits d'execution."""

    def __init__(self, **kwargs):
        self.tool_profile = validate_profile(setting("ROMEO_TOOL_PROFILE", "full"))
        super().__init__(**kwargs)

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
