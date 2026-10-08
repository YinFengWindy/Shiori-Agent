from __future__ import annotations
from typing import Any, cast

from pathlib import Path

import pytest

from agent.core import prompt_block
from agent.core.prompt_block import (
    ActiveSkillsPromptBlock,
    AffectionPromptBlock,
    BehaviorRulesPromptBlock,
    IdentityPromptBlock,
    LongTermMemoryPromptBlock,
    MemoryBlockPromptBlock,
    RecentContextPromptBlock,
    SelfModelPromptBlock,
    SessionContextPromptBlock,
    SkillsCatalogPromptBlock,
    SystemPromptBuilder,
    TurnContext,
    UserIdentitiesPromptBlock,
    build_role_user_identities_prompt,
)
from conversation.context_scope import ContextScope
from core.identity import IdentityChat
from core.memory.markdown_schema import SELF_PERSONA_SECTION
from core.roles import RoleStore
from core.roles.relationship_runtime.affection_prompts import (
    DEFAULT_AFFECTION_STAGE_PROMPTS,
)
from core.roles.relationship_runtime.affection_service import RoleAffectionService
from prompts.agent import build_agent_static_identity_prompt


class _Memory:
    def read_profile(self) -> str:
        return "memory block"

    def read_self(self) -> str:
        return "self note"


class _Skills:
    def get_always_skills(self) -> list[str]:
        return ["always"]

    def load_skills_for_context(self, names: list[str]) -> str:
        return "\n".join(names)

    def build_skills_summary(self) -> str:
        return "summary"


def test_system_prompt_builder_uses_prompt_blocks_and_static_cache(tmp_path: Path):
    builder = SystemPromptBuilder(
        [
            IdentityPromptBlock(render_fn=lambda **_: "identity"),
            MemoryBlockPromptBlock(),
        ]
    )
    ctx = TurnContext(
        workspace=tmp_path,
        memory=cast(Any, _Memory()),
        skills=cast(Any, _Skills()),
        skill_names=[],
        channel=None,
        chat_id=None,
        retrieved_memory_block="retrieved",
    )

    first = builder.build(ctx)
    second = builder.build(ctx)

    assert first.system_prompt == "identity\n\n---\n\nretrieved"
    assert [item.name for item in first.system_sections] == [
        "identity",
        "retrieved_memory",
    ]
    assert second.debug_breakdown[0].cache_hit is True


def test_system_prompt_builder_respects_disabled_sections(tmp_path: Path):
    builder = SystemPromptBuilder(
        [
            IdentityPromptBlock(render_fn=lambda **_: "identity"),
            MemoryBlockPromptBlock(),
        ]
    )
    ctx = TurnContext(
        workspace=tmp_path,
        memory=cast(Any, _Memory()),
        skills=cast(Any, _Skills()),
        skill_names=[],
        channel=None,
        chat_id=None,
        retrieved_memory_block="retrieved",
    )

    built = builder.build(ctx, disabled_sections={"retrieved_memory"})

    assert built.system_prompt == "identity"
    assert [item.name for item in built.system_sections] == ["identity"]


def test_static_identity_prompt_is_not_hardcoded_to_specific_user(tmp_path: Path):
    prompt = build_agent_static_identity_prompt(workspace=tmp_path)

    assert "花月的长期 AI 伙伴" not in prompt
    assert "用户的长期 AI 伙伴" not in prompt
    assert "roles/<role_id>/memory/" in prompt
    assert "不存在工作区级全局记忆兜底" in prompt


def test_prompt_block_priorities_leave_spacing_for_future_inserts():
    priorities = [
        (IdentityPromptBlock.label, IdentityPromptBlock.priority),
        (BehaviorRulesPromptBlock.label, BehaviorRulesPromptBlock.priority),
        (SkillsCatalogPromptBlock.label, SkillsCatalogPromptBlock.priority),
        (SelfModelPromptBlock.label, SelfModelPromptBlock.priority),
        (LongTermMemoryPromptBlock.label, LongTermMemoryPromptBlock.priority),
        (SessionContextPromptBlock.label, SessionContextPromptBlock.priority),
        (UserIdentitiesPromptBlock.label, UserIdentitiesPromptBlock.priority),
        (RecentContextPromptBlock.label, RecentContextPromptBlock.priority),
        (ActiveSkillsPromptBlock.label, ActiveSkillsPromptBlock.priority),
        (MemoryBlockPromptBlock.label, MemoryBlockPromptBlock.priority),
    ]

    assert priorities == [
        ("identity", 10),
        ("behavior_rules", 15),
        ("skills_catalog", 20),
        ("self_model", 30),
        ("long_term_memory", 35),
        ("session_context", 40),
        ("user_identities", 42),
        ("recent_context", 45),
        ("active_skills", 50),
        ("retrieved_memory", 55),
    ]


def _pair(store: RoleStore, record, user_id: str, scope, chat_id: str) -> None:
    identity = store.identities.pair(
        store.identities.create_pairing_code().code,
        record=record,
        user_id=user_id,
        scope=scope,
        chat=IdentityChat(record.id, record.plugin_id, chat_id),
    )
    assert identity is not None


def _roles(tmp_path: Path) -> tuple[RoleStore, dict[tuple[str, str], Any]]:
    """Mira owns QQ and QQBot accounts; Other owns QQ, Feishu and Telegram ones."""
    store = RoleStore(tmp_path)
    for role_id in ("mira", "other"):
        store.create_role(role_id=role_id, name=role_id, system_prompt="role")
    records = {
        (plugin_id, role_id): store.accounts.register(
            plugin_id=plugin_id,
            platform=plugin_id,
            platform_account_id=f"{plugin_id}-{role_id}",
            config_ref=f"{plugin_id}-{role_id}",
            token="live",
            role_id=role_id,
        ).record
        for plugin_id, role_id in (
            ("qq", "mira"),
            ("qqbot", "mira"),
            ("qq", "other"),
            ("feishu", "other"),
            ("telegram", "other"),
        )
    }
    return store, records


def test_user_identities_prompt_lists_the_bindings_reaching_the_roles_accounts(
    tmp_path: Path,
):
    store, records = _roles(tmp_path)
    # Platform-wide, but paired through Other's QQ account: no chat with Mira's.
    _pair(store, records[("qq", "other")], "3174898512", "platform", "3174898512")
    _pair(store, records[("qqbot", "mira")], "openid-1", "account", "c2c:app:openid-1")
    # Account-scoped to Other's account, or on a channel Mira has no account on.
    _pair(store, records[("feishu", "other")], "ou_other", "account", "oc_1")
    _pair(store, records[("telegram", "other")], "555", "platform", "555")

    assert build_role_user_identities_prompt("mira", store) == (
        "## 你的用户在各渠道的身份\n"
        "- 渠道 qq：3174898512（整个平台通用；尚无私聊）\n"
        "- 渠道 qqbot：openid-1（仅限你在该渠道的账号；私聊 qqbot:c2c:app:openid-1）\n"
        "群聊里有人提到或 @ 这些 ID 时，指的就是你的用户。"
    )


def test_user_identities_block_renders_nothing_without_a_role_or_bindings(
    tmp_path: Path,
):
    store, records = _roles(tmp_path)
    block = UserIdentitiesPromptBlock(store)

    def ctx(role_id: str) -> TurnContext:
        return TurnContext(
            workspace=tmp_path,
            memory=cast(Any, _Memory()),
            skills=cast(Any, _Skills()),
            skill_names=[],
            channel=None,
            chat_id=None,
            retrieved_memory_block="",
            role_id=role_id,
        )

    assert block.render(ctx("mira")) is None
    _pair(store, records[("qq", "mira")], "3174898512", "platform", "3174898512")
    assert block.render(ctx("")) is None
    assert "3174898512" in (block.render(ctx("mira")) or "")


class _SelfMemory(_Memory):
    def read_self(self) -> str:
        return "## 我的性格与形象\n- 形象条目\n\n## 我们的关系\n- 关系条目\n"


def _affection_ctx(tmp_path: Path, scope: ContextScope | None = None) -> TurnContext:
    return TurnContext(
        workspace=tmp_path,
        memory=cast(Any, _SelfMemory()),
        skills=cast(Any, _Skills()),
        skill_names=[],
        channel=None,
        chat_id=None,
        retrieved_memory_block="",
        role_id="mira",
        context_scope=scope,
    )


def test_affection_block_injects_the_current_stages_override_or_default(
    tmp_path: Path,
):
    store = RoleStore(tmp_path)
    store.create_role(role_id="mira", name="Mira", system_prompt="规则")
    block = AffectionPromptBlock(store)
    ctx = _affection_ctx(tmp_path)
    assert block.render(ctx) is None

    affection = RoleAffectionService(tmp_path)
    affection.initialize("mira", value=38, reason="初始")
    rendered = block.render(ctx) or ""
    assert "38（熟悉，范围 -100 到 100）" in rendered
    assert DEFAULT_AFFECTION_STAGE_PROMPTS["熟悉"] in rendered

    store.update_role(
        "mira",
        change_affection_stage_prompts=lambda current: {
            **current,
            "熟悉": "叫他笨蛋，嘴硬心软。",
        },
    )
    rendered = block.render(ctx) or ""
    assert "叫他笨蛋，嘴硬心软。" in rendered
    assert DEFAULT_AFFECTION_STAGE_PROMPTS["熟悉"] not in rendered

    # Crossing into the next stage switches to that stage's guidance.
    affection.apply_delta("mira", delta=3, reason="夸奖", source="turn")
    rendered = block.render(ctx) or ""
    assert "41（朋友，范围 -100 到 100）" in rendered
    assert DEFAULT_AFFECTION_STAGE_PROMPTS["朋友"] in rendered
    assert "叫他笨蛋" not in rendered


def test_affection_block_follows_the_relationship_sections_visibility(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    store = RoleStore(tmp_path)
    store.create_role(role_id="mira", name="Mira", system_prompt="规则")
    RoleAffectionService(tmp_path).initialize("mira", value=65, reason="初始")
    affection, self_model = AffectionPromptBlock(store), SelfModelPromptBlock()

    def visible(scope: ContextScope) -> tuple[bool, bool]:
        ctx = _affection_ctx(tmp_path, scope)
        return (
            "关系条目" in (self_model.render(ctx) or ""),
            affection.render(ctx) is not None,
        )

    assert visible("user") == (True, True)
    assert visible("external") == (True, True)
    # Hiding 「我们的关系」 from external turns hides the affection block with it.
    monkeypatch.setattr(prompt_block, "EXTERNAL_SELF_SECTIONS", (SELF_PERSONA_SECTION,))
    assert visible("external") == (False, False)
    assert visible("user") == (True, True)
