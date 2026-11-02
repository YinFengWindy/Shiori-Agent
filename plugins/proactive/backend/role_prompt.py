"""Role-scoped proactive guidance contributed to ordinary chat prompts."""

from dataclasses import replace
from pathlib import Path

from shiori_sdk.core.conversation import PromptRendering
from shiori_sdk.prompting import PromptSectionRender
from shiori_sdk.roles import Roles

from .context_panel import PROACTIVE_CONTEXT_FILE


async def append_proactive_prompt(
    event: PromptRendering, *, workspace: Path, roles: Roles
) -> PromptRendering:
    """Adds guidance only for an existing role while this plugin is loaded."""
    role_id = str(event.session_metadata.get("role_id") or "").strip()
    if not role_id or event.minimal_request or "proactive" in event.disabled_sections:
        return event
    if roles.get_role(role_id) is None:
        return event
    rules_path = str((workspace / "roles" / role_id / PROACTIVE_CONTEXT_FILE).resolve())
    section = PromptSectionRender(
        name="proactive",
        is_static=False,
        content=f"""- 主动规则面板：{rules_path}
  这是 proactive 链路专用规则文件，用来记录主动推送白名单、黑名单、过滤条件、前置验证要求。
  当用户明确修改“以后主动推送怎么做”时，应优先更新这里，而不是只停留在普通回复或长期记忆里。

### 主动链路资产
- 系统里除了当前被动回复链路，还存在 proactive 和 drift 两条后台链路。
- proactive 负责在合适时机主动触达用户；它会读取 `RECENT_CONTEXT.md` 和 `PROACTIVE_CONTEXT.md`。
- drift 负责在没有合适主动消息时，基于长期记忆和 `RECENT_CONTEXT.md` 自主做一点有意义的小事。
- 你不需要在被动回复时模拟 proactive / drift 的内部执行流程，但要知道它们会使用这些资产。
- 如果用户明确要求“以后主动推送别发什么/多发什么/先验证什么/只在什么条件下发”，这是 proactive 规则，不是普通聊天备注；应维护到 `PROACTIVE_CONTEXT.md`。
- 如果用户明确要求的是长期稳定偏好、身份事实、习惯、禁忌，则按普通记忆协议处理，不要一律写进 `PROACTIVE_CONTEXT.md`。""",
    )
    return replace(
        event, system_sections_bottom=(*event.system_sections_bottom, section)
    )
