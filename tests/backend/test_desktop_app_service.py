from __future__ import annotations

import pytest

from core.roles import RoleAggregateService, RoleStore
from conversation.service import ConversationService
from desktop_bridge.app_service import DesktopAppService
from session.manager import SessionManager


@pytest.mark.asyncio
async def test_desktop_app_service_open_role_session_ensures_formal_thread(
    tmp_path,
):
    role_store = RoleStore(tmp_path)
    session_manager = SessionManager(tmp_path)
    role_service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=session_manager,
    )
    aggregate = role_service.create_role(
        role_id="mira",
        name="Mira",
        description="desktop role",
        system_prompt="you are mira",
    )
    service = DesktopAppService(
        role_service=role_service,
        session_manager=session_manager,
        conversation_service=ConversationService(session_manager),
    )

    opened = await service.open_role_session(aggregate.role.id)

    assert opened.session.key == "role:mira"
    assert "thread_id" not in opened.session.metadata
    thread = session_manager.conversation_store.get_thread_by_legacy_session_key(
        "role:mira"
    )
    assert thread is not None
    assert thread.thread_kind == "desktop"
