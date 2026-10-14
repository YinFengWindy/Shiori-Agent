"""Settings rendered by the host's standard plugin configuration form."""

from typing import Literal

from pydantic import BaseModel, Field

type AgentKind = Literal["codex", "claude"]


class HerdrConfig(BaseModel):
    """Explicit local session and Full Access agent launch settings."""

    executable: str = Field(default="herdr", min_length=1, title="Herdr 路径")
    session: str = Field(
        default="shiori", pattern=r"^[a-zA-Z0-9_-]+$", title="Herdr Session"
    )
    default_agent: AgentKind = Field(default="codex", title="默认 Agent")
    codex_model: str = Field(default="", title="Codex 模型")
    claude_model: str = Field(default="", title="Claude Code 模型")
    cli_timeout_seconds: int = Field(default=45, ge=5, le=300, title="CLI 超时（秒）")
    task_timeout_seconds: int = Field(
        default=7200, ge=60, le=86400, title="任务追踪超时（秒）"
    )

    def agent_args(self, kind: AgentKind) -> list[str]:
        """Use only the explicitly selected agent's native Full Access flags."""
        args = [
            (
                "--dangerously-bypass-approvals-and-sandbox"
                if kind == "codex"
                else "--dangerously-skip-permissions"
            )
        ]
        model = self.codex_model if kind == "codex" else self.claude_model
        if model.strip():
            args.extend(["--model", model.strip()])
        return args
