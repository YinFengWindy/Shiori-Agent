"""The conversation plugin capabilities (#901 P2).

- ``HostBackgroundResults`` is the ``host.background_results`` core service:
  bound, role-serial result reporting for plugin-owned asynchronous work.
- ``HostExternalTurns`` is the ``host.external_turns`` core service (#721).
  A plugin-submitted message is routed exactly like a group message a channel
  account admitted (``core.channels.role_routing``) and runs through
  ``AgentLoop.process_external_turn``: never queued behind other role work,
  never dispatched to a channel. Routing happens only once the role's turn gate
  is held, so a busy role leaves no trace of the submission.

  The submitting plugin is trusted to speak for the role it names, as with any
  plugin capability; the host only checks that the role exists and that the
  platform is not the desktop or a channel the host runs, so a plugin cannot
  write into another transport's conversations.
- ``PluginBotCommands`` is the ``host.bot_commands`` core service: each
  plugin's command-menu entries, read back for the active plugins in kernel
  order.

The first two are one instance per kernel generation, built by bootstrap over
that generation's agent loop and shared by every plugin.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from shiori_sdk.accounts import AccountAccess
from shiori_sdk.background_results import BackgroundResultTarget
from shiori_sdk.channels.chat_types import CHAT_TYPE_GROUP
from shiori_sdk.channels.message_source import GROUP_NAME_KEY, SENDER_NAME_KEY
from shiori_sdk.external_turns import ExternalTurnMessage, ExternalTurnResult
from shiori_sdk.messages import InboundMessage

from agent.plugin_host.capabilities import ContributionsByPlugin, contribute_to_list
from agent.plugin_host.core_keys import HOST_BOT_COMMANDS, PluginBinding
from agent.tools.registry import ToolRegistry
from agent.tools.turn_origin import current_tool_origin
from agent.tools.turn_scope import current_tool_turn
from conversation.service import ConversationService
from core.accounts.tool_access import account_allows_full_tools
from core.channels.role_routing import CONVERSATION_DUPLICATE_KEY, RoleTurnRouter
from core.common.channel_directory import ChannelDirectory
from core.roles.errors import RoleNotFoundError
from core.roles.role_runtime import RoleExecutionContext
from core.roles.store import RoleStore

if TYPE_CHECKING:
    from agent.plugin_host import PluginKernel

type ResultRunner = Callable[
    [RoleExecutionContext, Callable[[], InboundMessage]], Awaitable[None]
]


@dataclass(frozen=True)
class _Target:
    role_id: str
    thread_id: str
    channel: str
    chat_id: str
    sender_id: str
    chat_type: str
    roles: RoleStore
    conversations: ConversationService
    run: ResultRunner
    metadata: dict[str, Any]
    account_access: AccountAccess | None = None
    attempted: set[str] = field(default_factory=set)

    def validate(self) -> None:
        thread = self.conversations.get_thread(self.thread_id)
        if (
            thread is None
            or thread.archived
            or thread.role_id != self.role_id
            or thread.channel != self.channel
            or (self.channel != "desktop" and thread.external_thread_id != self.chat_id)
        ):
            raise ValueError("后台结果的原会话已失效")
        if self.roles.get_role(self.role_id) is None:
            raise ValueError("后台结果的原角色已删除")
        if self.account_access is not None:
            origin = InboundMessage(
                channel=self.channel,
                chat_id=self.chat_id,
                sender=self.sender_id,
                content="",
                metadata=self.metadata,
            )
            if not self.roles.accounts.validate_access(
                self.account_access
            ) or not account_allows_full_tools(
                self.roles.accounts, origin, role_id=self.role_id
            ):
                raise PermissionError("后台结果的原连接或工具授权已失效")
        elif self.channel != "desktop" and not self.roles.bound_user_senders(
            self.role_id
        ).recognises(self.channel, self.sender_id):
            raise PermissionError("后台结果的原用户绑定已失效")

    async def report(self, result_id: str, text: str) -> bool:
        if not result_id.strip() or not text.strip():
            raise ValueError("后台结果标识和正文不能为空")
        if result_id in self.attempted:
            return False
        self.validate()
        role = self.roles.get_role(self.role_id)
        assert role is not None
        context = RoleExecutionContext.create(
            role=role,
            thread_id=self.thread_id,
            transport_channel=self.channel,
            transport_chat_id=self.chat_id,
            source="background_result",
            work_kind="passive_turn",
            request_id=result_id,
        )

        def admit() -> InboundMessage:
            # Binding/thread changes while waiting for another role turn must
            # be checked inside the same gate that admits the report.
            self.validate()
            return InboundMessage(
                channel=self.channel,
                chat_id=self.chat_id,
                sender=self.sender_id,
                content=(
                    "[后台任务结果] 请以你的角色向发起方汇报以下结果、验证与阻塞。"
                    "不要把待确认、仍在运行或缺失产物描述为完成；不要自动重试任务。\n\n"
                    + text
                ),
                metadata={
                    **self.metadata,
                    **context.to_metadata(),
                    "session_key_override": f"role:{self.role_id}",
                    "source": "background_result",
                    "chat_type": self.chat_type,
                    "omit_user_turn": True,
                    "skip_post_memory": True,
                    "suppress_stream_events": True,
                    "turn_id": result_id,
                    "background_result_text": text,
                },
            )

        self.attempted.add(result_id)
        await self.run(context, admit)
        return True


class HostBackgroundResults:
    """Capture the host's current tool context and retain no plugin-supplied route."""

    def __init__(
        self,
        tools: ToolRegistry,
        roles: RoleStore,
        conversations: ConversationService,
        run: ResultRunner,
    ) -> None:
        self._tools = tools
        self._roles = roles
        self._conversations = conversations
        self._run = run

    def capture(self) -> BackgroundResultTarget:
        """Only a live user or explicitly authorized account turn may start work."""
        _ = current_tool_turn()
        context = self._tools.get_context()
        if (
            context.get("sender_is_user") != "true"
            and context.get("account_full_tools") != "true"
        ):
            raise PermissionError("后台任务必须由用户本人或获完整工具授权的连接发起")
        role_id, thread_id, sender_id = (
            context.get(key, "") for key in ("role_id", "thread_id", "sender_id")
        )
        if not all((role_id, thread_id, sender_id)):
            raise ValueError("后台任务缺少原角色、线程或渠道身份")
        origin = current_tool_origin()
        is_user = context.get("sender_is_user") == "true"
        if not is_user and not account_allows_full_tools(
            self._roles.accounts, origin, role_id=role_id
        ):
            raise PermissionError("后台任务需要用户身份或完整工具授权")
        if (
            origin.metadata.get("role_id") != role_id
            or origin.metadata.get("thread_id") != thread_id
            or origin.sender != sender_id
        ):
            raise ValueError("后台任务身份与真实入站不一致")
        if origin.metadata.get("source") == "background_result":
            raise PermissionError("结果汇报不能冒充新的用户任务")
        metadata = dict(origin.metadata)
        # Preserve opaque channel delivery data (topics/accounts), but this
        # report is not another copy of the original incoming message.
        for key in (
            "external_message_id",
            "message_id",
            "reply_to_content",
            "reply_to_media",
        ):
            metadata.pop(key, None)
        target = _Target(
            role_id,
            thread_id,
            origin.channel,
            origin.chat_id,
            sender_id,
            str(metadata.get("chat_type") or ""),
            self._roles,
            self._conversations,
            self._run,
            metadata,
            account_access=(
                self._roles.accounts.authorize(str(metadata["account_id"]), role_id)
                if not is_user
                else None
            ),
        )
        target.validate()
        return target


# Role execution source of plugin-submitted turns (channel accounts use
# ``role_account``).
EXTERNAL_TURN_SOURCE = "external_turn"

# Routes the turn once the gate is held; None when it is a duplicate.
type ExternalTurnAdmission = Callable[[], InboundMessage | None]
# ``AgentLoop.process_external_turn``.
type ExternalTurnRunner = Callable[
    [RoleExecutionContext, ExternalTurnAdmission], Awaitable[ExternalTurnResult]
]


class HostExternalTurns:
    """Routes submitted messages as group-chat turns and runs them at once."""

    def __init__(
        self,
        router: RoleTurnRouter,
        run_turn: ExternalTurnRunner,
        *,
        channel_directory: ChannelDirectory,
    ) -> None:
        self._router = router
        self._run_turn = run_turn
        self._channels = channel_directory

    async def submit(self, message: ExternalTurnMessage) -> ExternalTurnResult:
        """Runs ``message`` as an external-context turn of its role.

        The conversation is a group chat named by its title, so the turn is
        judged external and the sender is never the bound user. Nothing is
        routed or stored unless the role's turn gate is taken; a message ID
        the conversation already holds runs nothing.
        """
        if self._channels.serves(message.platform):
            raise ValueError(f"外部回合不能使用宿主渠道名: {message.platform}")
        metadata: dict[str, object] = {
            "chat_type": CHAT_TYPE_GROUP,
            GROUP_NAME_KEY: message.conversation_title,
            SENDER_NAME_KEY: message.sender_name,
            "external_message_id": message.message_id,
            "source": EXTERNAL_TURN_SOURCE,
        }
        inbound = InboundMessage(
            channel=message.platform,
            sender=message.sender_id,
            chat_id=message.conversation_id,
            content=message.text,
            metadata=metadata,
        )
        try:
            context = self._router.network_turn_context(
                inbound, message.role_id, source=EXTERNAL_TURN_SOURCE
            )
        except RoleNotFoundError as error:
            raise ValueError(f"角色不存在: {message.role_id}") from error

        def admit() -> InboundMessage | None:
            routed = self._router.route(
                inbound, message.role_id, metadata, context=context
            )
            return None if routed.metadata.get(CONVERSATION_DUPLICATE_KEY) else routed

        return await self._run_turn(context, admit)


class PluginBotCommands(ContributionsByPlugin[tuple[str, str]]):
    """The ``host.bot_commands`` core service of one plugin kernel generation."""

    def for_plugin(self, binding: PluginBinding) -> BotCommandsCapability:
        """The bot commands capability of the plugin ``binding`` describes."""
        return BotCommandsCapability(self.of(binding.plugin_id), binding)


def active_plugin_bot_commands(kernel: PluginKernel) -> list[tuple[str, str]]:
    """The bot commands the generation's active plugins contributed, in kernel order."""
    source = kernel.core_service(HOST_BOT_COMMANDS)
    return list(source.active(kernel.active_plugin_ids))


class BotCommandsCapability:
    """贡献 bot 命令（如 Telegram `/xxx`）；卸载时随 effect 从聚合列表摘除。"""

    def __init__(self, commands: list[tuple[str, str]], binding: PluginBinding) -> None:
        self._commands = commands
        self._effects = binding.scope

    def add(self, command: str, description: str) -> None:
        """Lists ``/command`` with ``description`` until the plugin stops."""
        contribute_to_list(
            self._commands,
            (command, description),
            effects=self._effects,
            label=f"bot_command:{command}",
        )
