from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.roles import RoleAggregateService, RoleStore
from conversation.service import desktop_thread_id
from core.roles.model_runtime import RoleModelSnapshot
from core.roles.relationship_runtime import RoleAffectionService
from core.roles.relationship_runtime.affection_seed import (
    LlmAffectionSeedGenerator,
    RoleAffectionInitializer,
)
from core.roles.self_initializer import RoleSelfInitializer, SelfInitializationError
from core.roles.self_seed import LlmRoleSelfSeedGenerator
from session.manager import SessionManager


def _no_affection():
    # These tests cover SELF alone; affection seeding is covered further below.
    return SimpleNamespace(ensure_initialized=AsyncMock())


@pytest.fixture
def setup(tmp_path):
    store = RoleStore(tmp_path)
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=store,
        session_manager=SessionManager(tmp_path),
    )
    aggregate = service.create_role(
        name="Mira", role_id="mira", system_prompt="诚实", background="向导"
    )
    provider = SimpleNamespace(
        chat=AsyncMock(return_value=SimpleNamespace(content="# 我是谁\n\n生成内容\n"))
    )
    snapshot = RoleModelSnapshot(
        "selected", provider, "role-model", "none", role_id="mira"
    )
    initializer = RoleSelfInitializer(
        store, LlmRoleSelfSeedGenerator(), _no_affection()
    )
    return store, service, aggregate.memory_root / "SELF.md", snapshot, initializer


@pytest.mark.asyncio
async def test_seed_persists_success_and_survives_reopen_restart_and_rebinding(setup):
    store, service, path, snapshot, initializer = setup
    await initializer.ensure_seeded("mira", snapshot)
    saved = path.read_text(encoding="utf-8")
    state = store.get_role("mira").memory_init_state["self_seed"]
    assert state["status"] == "generated"
    assert state["model_registration_id"] == "selected"
    assert state["generated_at"] and state["last_attempt_at"]
    assert state["last_error"] is None
    service.open_role("mira")
    service.update_role(
        "mira",
        background="新背景",
        runtime_config={"dialogue_model_registration_id": "another"},
    )
    restarted = RoleSelfInitializer(
        RoleStore(store.workspace), LlmRoleSelfSeedGenerator(), _no_affection()
    )
    await restarted.ensure_seeded("mira", replace(snapshot, registration_id="another"))
    snapshot.provider.chat.assert_awaited_once()
    assert path.read_text(encoding="utf-8") == saved


@pytest.mark.asyncio
async def test_failed_seed_preserves_role_session_and_default_then_retries(setup):
    store, service, path, snapshot, initializer = setup
    default = path.read_text(encoding="utf-8")
    snapshot.provider.chat.side_effect = TimeoutError("provider timeout")
    with pytest.raises(SelfInitializationError, match="再次发送"):
        await initializer.ensure_seeded("mira", snapshot)
    state = store.get_role("mira").memory_init_state["self_seed"]
    assert state["status"] == "pending"
    assert state["last_error"] == "provider timeout"
    assert path.read_text(encoding="utf-8") == default
    assert service.open_role("mira").session.key == "role:mira"
    snapshot.provider.chat.side_effect = None
    restarted = RoleSelfInitializer(
        RoleStore(store.workspace), LlmRoleSelfSeedGenerator(), _no_affection()
    )
    await restarted.ensure_seeded("mira", snapshot)
    assert (
        store.get_role("mira").memory_init_state["self_seed"]["status"] == "generated"
    )
    assert snapshot.provider.chat.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("when", ["before", "during", "after"])
async def test_seed_never_overwrites_manual_edits(setup, when):
    store, service, path, snapshot, initializer = setup
    edited = "# 我是谁\n\n用户自己的内容\n"
    if when == "before":
        path.write_text(edited, encoding="utf-8")
    if when == "during":

        async def generate(**kwargs):
            path.write_text(edited, encoding="utf-8")
            return SimpleNamespace(content="新生成的内容")

        snapshot.provider.chat.side_effect = generate
    await initializer.ensure_seeded("mira", snapshot)
    if when == "after":
        path.write_text(edited, encoding="utf-8")
    service.open_role("mira")
    await initializer.ensure_seeded("mira", snapshot)
    assert path.read_text(encoding="utf-8") == edited
    assert snapshot.provider.chat.await_count == (0 if when == "before" else 1)
    assert store.get_role("mira").memory_init_state["self_seed"]["status"] == (
        "generated" if when == "after" else "user_edited"
    )


@pytest.mark.asyncio
async def test_pending_background_changes_during_generation_are_preserved(setup):
    store, service, path, snapshot, initializer = setup

    async def generate(**kwargs):
        service.update_role("mira", background="用户更新的背景")
        return SimpleNamespace(content="过期的生成内容")

    snapshot.provider.chat.side_effect = generate
    await initializer.ensure_seeded("mira", snapshot)
    assert "用户更新的背景" in path.read_text(encoding="utf-8")
    assert "过期的生成内容" not in path.read_text(encoding="utf-8")
    assert (
        store.get_role("mira").memory_init_state["self_seed"]["status"] == "user_edited"
    )


@pytest.mark.asyncio
async def test_cancelled_seed_remains_retryable(setup):
    store, _, path, snapshot, initializer = setup
    original = path.read_text(encoding="utf-8")
    snapshot.provider.chat.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await initializer.ensure_seeded("mira", snapshot)
    assert store.get_role("mira").memory_init_state["self_seed"]["status"] == "pending"
    assert path.read_text(encoding="utf-8") == original


@pytest.mark.asyncio
async def test_failure_does_not_reset_an_edit_saved_during_generation(setup):
    store, service, path, snapshot, initializer = setup

    async def generate(**kwargs):
        path.write_text("用户编辑", encoding="utf-8")
        service.open_role("mira")
        raise RuntimeError("failed after edit")

    snapshot.provider.chat.side_effect = generate
    with pytest.raises(SelfInitializationError):
        await initializer.ensure_seeded("mira", snapshot)
    state = store.get_role("mira").memory_init_state["self_seed"]
    assert state["status"] == "user_edited"
    assert state["last_error"] == "failed after edit"


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [{"purpose": "vision"}, {"role_id": "another"}])
async def test_seed_rejects_wrong_model_snapshot(setup, changes):
    _, _, _, snapshot, initializer = setup
    with pytest.raises(ValueError, match="对话模型"):
        await initializer.ensure_seeded("mira", replace(snapshot, **changes))
    snapshot.provider.chat.assert_not_called()


def _affection_initializer(tmp_path, session_manager):
    return RoleAffectionInitializer(
        tmp_path,
        session_manager=session_manager,
        generator=LlmAffectionSeedGenerator(),
    )


def _scripted_provider(affection_replies: list[str]):
    """Answers SELF seeding with a document and affection seeding from the script."""
    affection_prompts: list[str] = []

    async def chat(*, messages, **kwargs):
        if "初始好感度" not in messages[0]["content"]:
            return SimpleNamespace(content="# 我是谁\n\n生成内容\n")
        affection_prompts.append(messages[1]["content"])
        return SimpleNamespace(content=affection_replies.pop(0))

    return SimpleNamespace(chat=AsyncMock(side_effect=chat)), affection_prompts


@pytest.mark.asyncio
async def test_new_role_seeds_affection_from_profile_after_self(tmp_path):
    store, session_manager = RoleStore(tmp_path), SessionManager(tmp_path)
    RoleAggregateService.from_runtime(
        workspace=tmp_path, role_store=store, session_manager=session_manager
    ).create_role(name="Mira", role_id="mira", system_prompt="青梅竹马")
    provider, prompts = _scripted_provider(['{"value": 62, "reason": "从小一起长大"}'])
    initializer = RoleSelfInitializer(
        store,
        LlmRoleSelfSeedGenerator(),
        _affection_initializer(tmp_path, session_manager),
    )

    await initializer.ensure_seeded(
        "mira", RoleModelSnapshot("m", provider, "model", "none", role_id="mira")
    )

    affection = RoleAffectionService(tmp_path)
    assert affection.summary("mira")["stage"] == "亲密"
    [entry] = affection.read_history("mira")
    assert (entry.source, entry.after, entry.reason) == ("init", 62, "从小一起长大")
    assert "生成内容" in prompts[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("self_ready", [True, False])
async def test_affection_seed_always_sees_memory_and_conversation(tmp_path, self_ready):
    store, session_manager = RoleStore(tmp_path), SessionManager(tmp_path)
    aggregate = RoleAggregateService.from_runtime(
        workspace=tmp_path, role_store=store, session_manager=session_manager
    ).create_role(name="Mira", role_id="mira", system_prompt="诚实")
    if self_ready:
        (aggregate.memory_root / "SELF.md").write_text(
            "# 我是谁\n\n早就写好的自我\n", encoding="utf-8"
        )
    (aggregate.memory_root / "MEMORY.md").write_text(
        "# 长期记忆\n\n一起看过海\n", encoding="utf-8"
    )
    session = session_manager.get_or_create("role:mira")
    session.add_message("user", "今天也来找你了", thread_id=desktop_thread_id("mira"))
    provider, prompts = _scripted_provider(['{"value": 35, "reason": "常来聊天"}'])
    initializer = RoleSelfInitializer(
        store,
        LlmRoleSelfSeedGenerator(),
        _affection_initializer(tmp_path, session_manager),
    )

    await initializer.ensure_seeded(
        "mira", RoleModelSnapshot("m", provider, "model", "none", role_id="mira")
    )

    # Whether SELF was ready before or generated in this turn, history counts.
    assert provider.chat.await_count == (1 if self_ready else 2)
    assert ("早就写好的自我" if self_ready else "生成内容") in prompts[0]
    assert "一起看过海" in prompts[0] and "今天也来找你了" in prompts[0]
    assert RoleAffectionService(tmp_path).summary("mira")["value"] == 35


@pytest.mark.asyncio
async def test_failed_affection_seed_stops_the_turn_then_retries(tmp_path):
    store, session_manager = RoleStore(tmp_path), SessionManager(tmp_path)
    RoleAggregateService.from_runtime(
        workspace=tmp_path, role_store=store, session_manager=session_manager
    ).create_role(name="Mira", role_id="mira", system_prompt="诚实")
    provider, _ = _scripted_provider(
        ['{"value": 140, "reason": "越界"}', '{"value": 12, "reason": "初次见面"}']
    )
    initializer = RoleSelfInitializer(
        store,
        LlmRoleSelfSeedGenerator(),
        _affection_initializer(tmp_path, session_manager),
    )
    snapshot = RoleModelSnapshot("m", provider, "model", "none", role_id="mira")

    with pytest.raises(SelfInitializationError, match="好感度初始化失败"):
        await initializer.ensure_seeded("mira", snapshot)
    affection = RoleAffectionService(tmp_path)
    assert affection.read_state("mira") is None
    assert affection.read_history("mira") == []
    assert (
        store.get_role("mira").memory_init_state["self_seed"]["status"] == "generated"
    )

    await initializer.ensure_seeded("mira", snapshot)
    assert affection.summary("mira")["stage"] == "陌生"
    # SELF is not generated again; only affection is retried.
    assert provider.chat.await_count == 3
