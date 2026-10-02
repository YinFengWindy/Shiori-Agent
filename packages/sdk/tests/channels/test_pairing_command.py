from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

from shiori_sdk.messages import InboundMessage
from shiori_sdk.channels.pairing_command import answer_pairing_code

MESSAGE = InboundMessage(
    channel="qq",
    sender="902",
    chat_id="902",
    content="K7M2Q9XZ",
    metadata={"account_id": "qq:101", "chat_type": "private"},
)


async def test_a_consumed_code_is_confirmed_and_dropped() -> None:
    hub = SimpleNamespace(claim_pairing=MagicMock(return_value=True))
    send = AsyncMock()

    assert await answer_pairing_code(
        cast(Any, hub), MESSAGE, scope="platform", send=send
    )

    hub.claim_pairing.assert_called_once_with(MESSAGE, scope="platform")
    send.assert_awaited_once_with("已绑定")


async def test_other_text_is_left_to_the_role_without_a_reply() -> None:
    hub = SimpleNamespace(claim_pairing=MagicMock(return_value=False))
    send = AsyncMock()

    assert not await answer_pairing_code(
        cast(Any, hub), MESSAGE, scope="account", send=send
    )
    assert not await answer_pairing_code(None, MESSAGE, scope="account", send=send)
    send.assert_not_awaited()
