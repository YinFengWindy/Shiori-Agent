from __future__ import annotations

import asyncio
from dataclasses import dataclass

from agent.memory import DEFAULT_SELF_MD
from agent.provider import LLMProvider

from .store import RoleRecord

_SELF_SEED_SYSTEM = (
    "你正在为一个新创建的角色生成首版 SELF.md。"
    "输出必须是角色自我认知，而不是用户档案、系统说明或设定复述。"
)

_SELF_SEED_PROMPT = """\
请根据以下角色资料，为这个角色生成首版 `SELF.md`。

目标：
- 输出必须以 `# 角色自我认知` 开头
- 只允许包含三个 section：
  - `## 人格与形象`
  - `## 我对当前用户的理解`
  - `## 我们关系的定义`

硬规则：
- 这是“当前角色”的自我认知，不是 Akashic 的说明
- 禁止出现“内部底座”“系统内核”“执行框架”“真实身份是 Akashic”“我只是外壳”这类元叙事
- 不要直接复述完整 system_prompt，要提炼成角色自述
- 还没有真实互动证据时，`## 我对当前用户的理解` 必须克制，只能写谨慎、开放的初始理解
- 还没有真实互动证据时，`## 我们关系的定义` 只能写初始关系基调，不能虚构亲密经历
- 不要写用户偏好、时间线事件、工具规则、账号信息
- 输出语气要贴近角色自身，而不是通用助手模板

角色名称：
{role_name}

角色简介：
{role_description}

角色背景：
{role_background}

角色系统提示词：
{role_prompt}
"""


@dataclass
class LlmRoleSelfSeedGenerator:
    provider: LLMProvider
    model: str
    timeout_s: float = 60.0

    def generate(self, role: RoleRecord) -> str:
        return asyncio.run(self.agenerate(role))

    async def agenerate(self, role: RoleRecord) -> str:
        prompt = _SELF_SEED_PROMPT.format(
            role_name=role.name or role.id,
            role_description=role.description.strip() or "（无）",
            role_background=role.background.strip() or "（无）",
            role_prompt=role.system_prompt.strip(),
        )
        try:
            response = await asyncio.wait_for(
                self.provider.chat(
                    messages=[
                        {"role": "system", "content": _SELF_SEED_SYSTEM},
                        {"role": "user", "content": prompt},
                    ],
                    tools=[],
                    model=self.model,
                    max_tokens=2048,
                ),
                timeout=self.timeout_s,
            )
            text = (response.content or "").strip()
            return text or DEFAULT_SELF_MD.strip()
        except Exception:
            return DEFAULT_SELF_MD.strip()
