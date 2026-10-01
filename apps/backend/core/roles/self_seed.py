from __future__ import annotations

from .models import RoleRecord
from .model_runtime import RoleModelSnapshot
from .role_prompt_compiler import RolePromptCompiler

_SELF_SEED_SYSTEM = (
    "你正在为一个新创建的角色生成首版 SELF.md。"
    "输出必须是角色自我认知，而不是用户档案、系统说明或设定复述。"
)

_SELF_SEED_PROMPT = """\
请根据以下角色资料，为这个角色生成首版 `SELF.md`。

目标：
- 输出必须以 `# 我是谁` 开头
- 只允许包含三个 section：
  - `## 我的性格与形象`
  - `## 我对你的理解`
  - `## 我们的关系`

硬规则：
- 这是“当前角色”的自我认知，不是 Shiori 的说明
- 禁止出现“内部底座”“系统内核”“执行框架”“真实身份是 Shiori”“我只是外壳”这类元叙事
- 不要直接复述完整 system_prompt，要提炼成角色自述
- 还没有真实互动证据时，`## 我对你的理解` 必须克制，只能写谨慎、开放的初始理解
- 还没有真实互动证据时，`## 我们的关系` 只能写初始关系基调，不能虚构亲密经历
- 不要写用户偏好、时间线事件、工具规则、账号信息
- 输出语气要贴近角色自身，而不是通用助手模板

角色名称：
{role_name}

角色简介：
{role_description}

角色定义：
{role_prompt}
"""


class LlmRoleSelfSeedGenerator:
    """Generates SELF content using the dialogue snapshot accepted by the turn."""

    async def agenerate(self, role: RoleRecord, snapshot: RoleModelSnapshot) -> str:
        """Returns generated content, propagating provider failures and empty responses."""
        prompt = _SELF_SEED_PROMPT.format(
            role_name=role.name or role.id,
            role_description=role.description.strip() or "（无）",
            role_prompt=RolePromptCompiler().compile(role).content,
        )
        # Long role profiles and configured reasoning share the provider's normal
        # timeout; initialization does not impose an additional output budget.
        response = await snapshot.provider.chat(
            messages=[
                {"role": "system", "content": _SELF_SEED_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            tools=[],
            model=snapshot.model,
            max_tokens=None,
        )
        text = (response.content or "").strip()
        if not text:
            raise ValueError("SELF.md 初始化返回了空内容")
        return text
