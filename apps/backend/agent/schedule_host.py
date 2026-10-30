"""``SCHEDULE_HOST``: scheduled role turns and deliveries on the host.

The scheduler hands over a ``ScheduledRun``; this module turns it into the
role execution metadata the agent loop and role runtime read, and owns the
occurrence's delivery key.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from shiori_sdk.core.schedule_host import ScheduledRun

from agent.tools.message_push import MessagePushTool

# Tools a scheduled turn must not call: it delivers through ``deliver`` and
# leaves memory alone.
_SCHEDULED_TURN_DISABLED_TOOLS = (
    "message_push",
    "recall_memory",
    "memorize",
    "forget_memory",
)


class ScheduledRunLoop(Protocol):
    """The agent loop entry points a scheduled run goes through.

    The runtime dispatcher implements these on the currently published
    generation.
    """

    async def process_direct(
        self,
        content: str,
        *,
        session_key: str,
        channel: str,
        chat_id: str,
        omit_user_turn: bool,
        skip_post_memory: bool,
        skip_memory_retrieval: bool,
        disabled_tools: list[str] | None,
        metadata: dict[str, Any] | None,
    ) -> str: ...

    async def run_role_operation(
        self, metadata: dict[str, str], operation: Callable[[], Awaitable[Any]]
    ) -> Any: ...


def scheduled_run_metadata(run: ScheduledRun) -> dict[str, str]:
    """The role execution metadata of one scheduled occurrence.

    The delivery key names the job and its nominal fire time, so retries of
    the same occurrence and a restart share it.
    """
    return {
        "role_id": run.role_id,
        "role_config_version": run.role_config_version,
        "thread_id": run.thread_id,
        "delivery_key": f"scheduler:{run.job_id}:{run.fire_at.isoformat()}",
        "transport_channel": run.channel,
        "transport_chat_id": run.chat_id,
        "role_source": "scheduler",
        "role_work_kind": "scheduled_job",
        "request_id": run.job_id,
        "role_context_created_at": run.created_at.isoformat(),
    }


class HostScheduleRunner:
    """``SCHEDULE_HOST`` over the runtime dispatcher and the shared push tool.

    ``loop_provider`` returns the dispatcher, which pins each call to the
    currently published generation. One runner serves every generation.
    """

    def __init__(
        self,
        loop_provider: Callable[[], ScheduledRunLoop | None],
        push_tool: MessagePushTool,
    ) -> None:
        self._loop_provider = loop_provider
        self._push_tool = push_tool

    async def deliver(
        self, run: ScheduledRun, message: str, *, already_persisted: bool = False
    ) -> str:
        """Pushes ``message`` as the role inside the role's thread execution."""
        metadata = scheduled_run_metadata(run)
        return await self._loop().run_role_operation(
            metadata,
            lambda: self._push_tool.execute(
                channel=run.channel,
                chat_id=run.chat_id,
                message=message,
                role_id=run.role_id,
                push_delivery_key=metadata["delivery_key"],
                push_message_already_persisted=already_persisted,
            ),
        )

    async def run_turn(self, run: ScheduledRun, prompt: str) -> str:
        """Runs one scheduled role turn without delivering its reply."""
        return await self._loop().process_direct(
            content=prompt,
            channel=run.channel,
            chat_id=run.chat_id,
            session_key=f"scheduler:{run.job_id}",
            omit_user_turn=True,
            skip_post_memory=True,
            skip_memory_retrieval=True,
            disabled_tools=list(_SCHEDULED_TURN_DISABLED_TOOLS),
            metadata=scheduled_run_metadata(run),
        )

    def _loop(self) -> ScheduledRunLoop:
        loop = self._loop_provider()
        if loop is None:
            raise RuntimeError("计划任务需要已启动的运行时")
        return loop
