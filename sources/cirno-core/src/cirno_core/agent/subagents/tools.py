"""Isolated task capabilities and their workspace-aware system prompt."""

from __future__ import annotations

from pathlib import Path
from collections.abc import Callable

from cirno_core.agent.tools.context import ToolContext
from cirno_core.agent.tools.file_state import FileStates
from cirno_core.agent.tools.loader import ToolLoader
from cirno_core.agent.tools.registry import ToolRegistry
from cirno_core.config.network import NetworkConfig
from cirno_core.config.prompts import SystemPrompts
from cirno_core.config.tools import ToolsConfig
from cirno_core.processes.sessions import ExecSessionManager
from cirno_core.security.workspace_access import workspace_sandbox_status
from cirno_core.utils.prompt_templates import render_template


class SubagentTools:
    def __init__(
        self,
        workspace: Path,
        config: ToolsConfig,
        network: NetworkConfig,
        restrict_to_workspace: bool,
        disabled_skills: set[str],
        always_skills: set[str] | None = None,
    ):
        self.workspace = workspace
        self.config = config
        self.network = network
        self.restrict_to_workspace = restrict_to_workspace
        self.disabled_skills = disabled_skills
        self.always_skills = always_skills or set()
        self.system_prompts = SystemPrompts()
        self.system_prompts_loader: Callable[[], SystemPrompts] | None = None

    def configuration(self) -> ToolsConfig:
        """Build a ToolsConfig scoped for subagent use."""
        return ToolsConfig(
            exec=self.config.exec,
            web=self.config.web,
            file=self.config.file,
            restrict_to_workspace=self.restrict_to_workspace,
        )

    def build(
        self,
        *,
        exec_manager: ExecSessionManager,
        workspace: Path | None = None,
        tools_config: ToolsConfig | None = None,
    ) -> ToolRegistry:
        """Build an isolated subagent tool registry via ToolLoader."""
        root = self.workspace if workspace is None else workspace
        registry = ToolRegistry()
        cfg = tools_config if tools_config is not None else self.configuration()
        ctx = ToolContext(
            config=cfg,
            network=self.network,
            workspace=str(root.resolve()),
            exec_session_manager=exec_manager,
            file_state_store=FileStates(),
            workspace_sandbox=workspace_sandbox_status(
                restrict_to_workspace=cfg.restrict_to_workspace,
                workspace=root,
            ),
        )
        ToolLoader().load(ctx, registry, scope="subagent")
        return registry

    def prompt(self, workspace: Path | None = None) -> str:
        """Build a focused system prompt for the subagent."""
        from cirno_core.skills.context import SkillContext
        from cirno_core.skills.loader import SkillsLoader

        agent_workspace = self.workspace.expanduser().resolve()
        project_workspace = workspace.expanduser().resolve() if workspace else agent_workspace
        system_prompts = self.system_prompts_loader() if self.system_prompts_loader else self.system_prompts
        catalog = SkillsLoader(self.workspace, disabled_skills=self.disabled_skills, always_skills=self.always_skills)
        skill_context = SkillContext(catalog)
        with catalog.snapshot():
            active = catalog.get_always_skills()
            active_content = skill_context.load_skills_for_context(active)
            skills_summary = skill_context.build_skills_summary(exclude=set(active), workspace=project_workspace)
        if active_content:
            skills_summary = "# Active Skills\n\n" + active_content + "\n\n" + skills_summary
        from cirno_core.config.home import get_home_path

        agent_home = get_home_path().resolve()
        history_log = (
            str(agent_home / "memory" / "history.jsonl")
            if agent_home != project_workspace
            else "memory/history.jsonl"
        )
        return render_template(
            "agent/subagent_system.md",
            workspace=str(project_workspace),
            agent_workspace=str(agent_home),
            history_log=history_log,
            skills_summary=skills_summary or "",
            system_prompt_additions=system_prompts.for_role("worker"),
        )
