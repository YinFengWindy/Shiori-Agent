"""Minimal instant-message prompt with host-owned message delivery."""

from shiori_sdk.lifecycle import LifecycleFrame, PromptRenderCtx
from shiori_sdk.plugin_services import ServicePluginContext
from shiori_sdk.prompting import PromptSectionRender
from shiori_sdk.reply_sequence import ReplySequencePolicy
from shiori_sdk.role_events import RoleDeleted

from .role_state import PLUGIN_ID, NaturalChatRoleState

SEPARATOR = "<message-break/>"


class NaturalChatPromptModule:
    """Opt the current supported role turn into complete-message presentation."""

    slot = "natural_chat.prompt"
    requires = ("prompt_render.emit", "prompt:ctx")
    produces = ("prompt:ctx",)

    def __init__(self, state: NaturalChatRoleState) -> None:
        self._state = state

    async def run[FrameT: LifecycleFrame](self, frame: FrameT) -> FrameT:
        """Let the model choose all wording and message boundaries itself."""
        ctx = frame.slots["prompt:ctx"]
        if not isinstance(ctx, PromptRenderCtx):
            raise TypeError("prompt:ctx must be PromptRenderCtx")
        role_id = str(ctx.session_metadata.get("role_id") or "")
        if not ctx.supports_reply_sequence or not self._state.enabled(role_id):
            return frame
        ctx.reply_sequence = ReplySequencePolicy(SEPARATOR)
        ctx.system_sections_bottom.append(
            PromptSectionRender(
                name="natural_chat",
                content=(
                    "## 即时聊天\n"
                    "你正在即时聊天，可以按需要发送一条或多条消息。"
                    "内容、措辞、条数和结束时机由你根据角色与当前对话决定。\n"
                    f"需要另发一条消息时，在两条消息之间单独写一行 {SEPARATOR}。"
                    "普通换行仍属于同一条消息；分隔符只放在非空消息之间，"
                    "不要放进代码块。"
                ),
                is_static=False,
            )
        )
        return frame


async def setup(ctx: ServicePluginContext) -> None:
    """Register the role draft and prompt module within the plugin lifetime."""
    state = NaturalChatRoleState(ctx.roles)
    state.reconcile()
    ctx.effect(
        "role_settings",
        ctx.roles.extensions.register(PLUGIN_ID, state.write_draft, state.project),
    )
    ctx.events.on(RoleDeleted, state.on_role_deleted)
    ctx.lifecycle.contribute("prompt_render", [NaturalChatPromptModule(state)])
