"""Desktop admission reads the role record, not the session copy."""

from plugins.natural_chat.backend.plugin import NaturalChatPolicy
from tests.support.generation_getters import turn_getters
from types import SimpleNamespace
from unittest.mock import AsyncMock

from core.roles.store import RoleStore
from desktop_bridge.chat_service import DesktopChatService
from session.manager import SessionManager
from session.manager.helpers import role_id_from_session_key


async def test_desktop_admission_reads_the_role_record_not_the_session_copy(tmp_path):
    roles = RoleStore(tmp_path)
    roles.create_role(
        role_id="mira",
        name="Mira",
        system_prompt="test",
        runtime_config={"natural_chat_enabled": True},
    )
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    session.metadata["role_id"] = "mira"
    session.metadata["role_runtime_config"] = {"natural_chat_enabled": False}
    manager.save(session)

    async def run_chat_turn(**_kwargs):
        return None

    service = DesktopChatService(
        agent_loop=SimpleNamespace(),
        event_bus=SimpleNamespace(),
        session_manager=manager,
        role_lookup=roles.get_role,
        role_id_from_session_key=role_id_from_session_key,
        sync_desktop_session_thread=lambda _session, *, role_id: None,
        emit_payload=AsyncMock(),
        emit_session_updated=AsyncMock(),
    )
    service.run_chat_turn = run_chat_turn
    # The bridge admits chat.send under the generation lease; its policy is on.
    with turn_getters(policy=NaturalChatPolicy()):
        service.start_chat_turn(
            request_id="req",
            session_key="role:mira",
            content="hello",
            media=[],
            metadata=None,
            omit_user_turn=True,
            emit_event=AsyncMock(),
        )

    turn = service._tasks_by_session["role:mira"]
    assert turn.reply_interruption is not None
    assert turn.reply_interruption.natural_chat is True
    await turn.task
