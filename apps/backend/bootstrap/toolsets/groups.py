"""群聊旁听控制的装配与群相关工具的注册（#540）。

``GroupListeningControl`` 在运行时里只装配这一份：设置旁听的工具与桌面小手机
（经 ``CoreRuntime.group_listening``）共用同一个实例与「渠道是否支持旁听」判定。
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from agent.plugin_host.manifest import PluginManifest, group_listening_channels
from agent.tools.group_listening import SetGroupListeningTool
from agent.tools.member_lookup import LookupMemberTool
from agent.tools.registry import ToolRegistry
from conversation.listening import GroupListeningControl
from conversation.service import ConversationService
from core.memory.member_profiles import MemberProfiles
from session.manager import SessionManager


def register_group_tools(
    tools: ToolRegistry,
    workspace: Path,
    session_manager: SessionManager,
    manifests: Iterable[PluginManifest],
) -> GroupListeningControl:
    """Registers the listening switch and the member-profile lookup tools.

    Returns the runtime's listening control, which the switch tool uses: a
    channel supports listening when its plugin manifest (among ``manifests``)
    declares ``group_listening``.
    """
    conversations = ConversationService(session_manager)
    listening = GroupListeningControl(
        conversations, group_listening_channels(manifests)
    )
    # 未声明外部可用：外部上下文里群友触发的回合拿不到（#489）。
    tools.register(
        SetGroupListeningTool(listening),
        risk="write",
        search_hint="旁听 看群 群消息",
    )
    # 查成员档案进外部上下文白名单。
    tools.register(
        LookupMemberTool(MemberProfiles(workspace), conversations),
        risk="read-only",
        search_hint="群友 昵称 是谁",
        external_allowed=True,
    )
    return listening
