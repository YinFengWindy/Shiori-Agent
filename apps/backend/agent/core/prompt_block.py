from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from agent.prompting import PromptSectionMeta, PromptSectionRender, SectionCache
from core.memory.markdown_schema import select_memory_sections
from prompts.agent import (
    build_agent_behavior_rules_prompt,
    build_agent_session_context_prompt,
    build_agent_static_identity_prompt,
    build_skills_catalog_prompt,
)

if TYPE_CHECKING:
    from agent.skills import SkillsLoader
    from conversation.context_scope import ContextScope
    from core.memory.markdown import MemoryProfileApi

logger = logging.getLogger("agent.core.prompt_block")


@dataclass
class TurnContext:
    workspace: Path
    memory: "MemoryProfileApi"
    skills: "SkillsLoader"
    skill_names: list[str]
    channel: str | None
    chat_id: str | None
    retrieved_memory_block: str
    # 回合所在的上下文（#482）；None 表示非角色共享会话，按用户上下文注入。
    context_scope: "ContextScope | None" = None


def is_external_turn(ctx: TurnContext) -> bool:
    """本回合是否落在外部上下文（群聊、陌生私聊）。

    外部回合不注入用户层记忆：长期记忆、RECENT_CONTEXT、引擎检索结果，
    SELF.md 也只注入 ``EXTERNAL_SELF_SECTIONS``（#495）。
    """
    return ctx.context_scope == "external"


# 外部回合可见的 SELF.md 段落：角色自己的形象，以及用户名片（关系定位与称呼）。
# 「我对你的理解」写的是对用户的理解，只在用户上下文注入。
EXTERNAL_SELF_SECTIONS = ("## 我的性格与形象", "## 我们的关系")


class PromptBlock(Protocol):
    priority: int
    label: str
    is_static: bool

    def render(
        self, ctx: TurnContext, cached_signature: str | None = None
    ) -> str | None: ...

    def cache_signature(self, ctx: TurnContext) -> str | None: ...


# ─── Prompt Block 渲染顺序（priority 升序 = system prompt 拼接顺序）────────────
#  10 IdentityPromptBlock      → build_agent_static_identity_prompt(workspace)
#                              来源：工作区路径、memory/* 文件索引
#                              时机：仅 workspace 变化时才变，最稳定
#  15 BehaviorRulesPromptBlock → build_agent_behavior_rules_prompt(workspace)
#                              来源：prompts/agent.py 里的固定行为规范
#                              时机：仅代码或 workspace 变化时才变，最稳定
#  20 SkillsCatalogPromptBlock → skills.build_skills_summary()
#                              来源：skills/ 目录扫描结果、技能描述、依赖可用性
#                              时机：技能文件或环境依赖变化时才变，低频
#  30 SelfModelPromptBlock     → roles/<role_id>/memory/SELF.md
#                              来源：memory.read_self()（严格要求 role_id）
#                              外部回合只取 EXTERNAL_SELF_SECTIONS 两段
#                              时机：自我认知被写回时才变，低频
#  35 LongTermMemoryPromptBlock→ roles/<role_id>/memory/MEMORY.md（外部回合不注入）
#                              来源：memory.read_profile() / get_memory_context()（严格要求 role_id）
#                              时机：长期记忆 consolidate 或人工更新时才变，低频
#  40 SessionContextPromptBlock→ 环境 + 当前 session
#                              来源：platform.machine() + channel + chat_id
#                              时机：切换机器架构、channel、chat_id 时才变；同 session 基本稳定
#  45 RecentContextPromptBlock → roles/<role_id>/memory/RECENT_CONTEXT.md（裁掉 Recent Turns；外部回合不注入）
#                              来源：memory.read_recent_context()（严格要求 role_id）
#                              时机：近期语境压缩摘要更新时变化；每轮 Recent Turns 刷新不会直接进入这里
#  50 ActiveSkillsPromptBlock  → active skill 内容
#                              来源：always skills + 本轮命中的 skill_names
#                              时机：本轮技能命中集合变化时就会变，中频
#  55 MemoryBlockPromptBlock   → 本轮语义检索注入（外部回合不注入）
#                              来源：retrieved_memory_block
#                              时机：每轮 retrieval 结果都可能不同，最高频
# ─────────────────────────────────────────────────────────────────────────────
class IdentityPromptBlock:
    priority = 10
    label = "identity"
    is_static = True

    def __init__(self, render_fn=build_agent_static_identity_prompt) -> None:
        self._render_fn = render_fn

    def render(
        self, ctx: TurnContext, cached_signature: str | None = None
    ) -> str | None:
        return self._render_fn(workspace=ctx.workspace)

    def cache_signature(self, ctx: TurnContext) -> str | None:
        return str(ctx.workspace.expanduser().resolve())


class BehaviorRulesPromptBlock:
    priority = 15
    label = "behavior_rules"
    is_static = True

    def __init__(self, render_fn=build_agent_behavior_rules_prompt) -> None:
        self._render_fn = render_fn

    def render(
        self, ctx: TurnContext, cached_signature: str | None = None
    ) -> str | None:
        return self._render_fn(workspace=ctx.workspace)

    def cache_signature(self, ctx: TurnContext) -> str | None:
        return str(ctx.workspace.expanduser().resolve())


class SkillsCatalogPromptBlock:
    priority = 20
    label = "skills_catalog"
    is_static = True

    def __init__(self, render_fn=build_skills_catalog_prompt) -> None:
        self._render_fn = render_fn

    def render(
        self, ctx: TurnContext, cached_signature: str | None = None
    ) -> str | None:
        summary = cached_signature or ""
        if not summary:
            return None
        return self._render_fn(summary)

    def cache_signature(self, ctx: TurnContext) -> str | None:
        summary = ctx.skills.build_skills_summary()
        return summary or None


class SelfModelPromptBlock:
    priority = 30
    label = "self_model"
    is_static = False

    def render(
        self, ctx: TurnContext, cached_signature: str | None = None
    ) -> str | None:
        self_content = ctx.memory.read_self()
        if self_content and is_external_turn(ctx):
            self_content = select_memory_sections(
                "SELF.md", self_content, EXTERNAL_SELF_SECTIONS
            )
        if not self_content:
            return None
        return f"## 角色自我认知\n\n{self_content}"

    def cache_signature(self, ctx: TurnContext) -> str | None:
        return None


class LongTermMemoryPromptBlock:
    priority = 35
    label = "long_term_memory"
    is_static = False

    def render(
        self, ctx: TurnContext, cached_signature: str | None = None
    ) -> str | None:
        if is_external_turn(ctx):
            return None
        memory = ctx.memory.get_memory_context()
        return str(memory).strip() if memory else None

    def cache_signature(self, ctx: TurnContext) -> str | None:
        return None


class SessionContextPromptBlock:
    priority = 40
    label = "session_context"
    is_static = False

    def __init__(self, render_fn=build_agent_session_context_prompt) -> None:
        self._render_fn = render_fn

    def render(
        self, ctx: TurnContext, cached_signature: str | None = None
    ) -> str | None:
        return self._render_fn(
            channel=ctx.channel,
            chat_id=ctx.chat_id,
        )

    def cache_signature(self, ctx: TurnContext) -> str | None:
        return None


def strip_recent_turns(recent_context: str) -> str:
    """RECENT_CONTEXT.md without its raw "recent turns" section.

    That section copies the newest raw messages of the whole role session,
    across every thread, so no model prompt shows it: passive turns get those
    messages through their context-filtered history window, and proactive
    turns read the user context through ``get_recent_chat``.
    """
    cuts = [
        cut
        for marker in ("\n## 最近的对话", "\n## Recent Turns")
        if (cut := recent_context.find(marker)) != -1
    ]
    return (recent_context[: min(cuts)] if cuts else recent_context).strip()


class RecentContextPromptBlock:
    priority = 45
    label = "recent_context"
    is_static = False

    def render(
        self, ctx: TurnContext, cached_signature: str | None = None
    ) -> str | None:
        if is_external_turn(ctx):
            return None
        return strip_recent_turns(ctx.memory.read_recent_context() or "") or None

    def cache_signature(self, ctx: TurnContext) -> str | None:
        return None


class ActiveSkillsPromptBlock:
    priority = 50
    label = "active_skills"
    is_static = False

    def render(
        self, ctx: TurnContext, cached_signature: str | None = None
    ) -> str | None:
        always_skills = ctx.skills.get_always_skills()
        names: list[str] = []
        seen: set[str] = set()
        for name in [*always_skills, *ctx.skill_names]:
            if name in seen:
                continue
            seen.add(name)
            names.append(name)
        if not names:
            return None
        content = ctx.skills.load_skills_for_context(names)
        if not content:
            return None
        return f"# Active Skills\n\n{content}"

    def cache_signature(self, ctx: TurnContext) -> str | None:
        return None


class MemoryBlockPromptBlock:
    priority = 55
    label = "retrieved_memory"
    is_static = False

    def render(
        self, ctx: TurnContext, cached_signature: str | None = None
    ) -> str | None:
        # 外部回合本就不检索；这里再挡住插件在 before_reasoning 写入的检索块。
        if is_external_turn(ctx):
            return None
        block = (ctx.retrieved_memory_block or "").strip()
        return block or None

    def cache_signature(self, ctx: TurnContext) -> str | None:
        return None


@dataclass
class SystemPromptBuildResult:
    system_sections: list[PromptSectionRender]
    system_prompt: str
    debug_breakdown: list[PromptSectionMeta]


class SystemPromptBuilder:
    """
    ┌──────────────────────────────────────┐
    │ SystemPromptBuilder                  │
    ├──────────────────────────────────────┤
    │ 1. 按 priority 遍历 prompt blocks    │
    │ 2. 读取 static block cache           │
    │ 3. 渲染启用的 blocks                 │
    │ 4. 汇总 system prompt               │
    └──────────────────────────────────────┘
    """

    def __init__(
        self,
        blocks: list[PromptBlock],
        cache: SectionCache | None = None,
    ) -> None:
        self._blocks = sorted(blocks, key=lambda block: block.priority)
        self._cache = cache or SectionCache()

    def build(
        self,
        ctx: TurnContext,
        *,
        disabled_sections: set[str] | None = None,
    ) -> SystemPromptBuildResult:
        # 1. 先准备输出容器和禁用集合。
        renders: list[PromptSectionRender] = []
        breakdown: list[PromptSectionMeta] = []
        disabled = disabled_sections or set()
        cache_scope = str(ctx.workspace.expanduser().resolve())

        # 2. 再逐个渲染 prompt block。
        for block in self._blocks:
            if block.label in disabled:
                continue
            cache_hit = False
            rendered: str | None = None
            signature = block.cache_signature(ctx) if block.is_static else None

            # 3. static block 先查缓存，避免重复读文件或重复构造。
            if signature:
                rendered = self._cache.get(cache_scope, block.label, signature)
                cache_hit = rendered is not None
            if rendered is None:
                rendered = block.render(ctx, cached_signature=signature)
                if rendered and signature:
                    self._cache.set(cache_scope, block.label, signature, rendered)

            # 4. 最后只收录真正有内容的 block。
            if rendered:
                renders.append(
                    PromptSectionRender(
                        name=block.label,
                        content=rendered,
                        is_static=block.is_static,
                        cache_hit=cache_hit,
                    )
                )
                breakdown.append(
                    PromptSectionMeta(
                        name=block.label,
                        chars=len(rendered),
                        est_tokens=max(1, len(rendered) // 3),
                        is_static=block.is_static,
                        cache_hit=cache_hit,
                    )
                )

        return SystemPromptBuildResult(
            system_sections=renders,
            system_prompt="\n\n---\n\n".join(item.content for item in renders),
            debug_breakdown=breakdown,
        )
