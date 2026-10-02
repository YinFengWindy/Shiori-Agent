"""A Telegram message travels the real host end to end and its reply is recorded.

The Telegram plugin is loaded by the real plugin kernel inside a full
``AppRuntime`` with message channels on: its Bot is added through the bridge
RPC the plugin UI uses, the inbound message is routed by the real
``ChannelHub`` onto the owning role's session, the real ``AgentLoop`` answers
it through ``MessageBus``, and the hub records the reply's delivery.

Only two boundaries are faked: the Telegram Bot API (python-telegram-bot's
``HTTPXRequest.do_request``, the single place every Bot API call goes out) and
the LLM provider that role model resolution instantiates.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from shiori_sdk.testing.bridge import plugin_bridge_request
from shiori_sdk.testing.packages import plugin_directory, stage_plugin_package
from telegram.request import HTTPXRequest, RequestData

from agent.config import load_config_text
from agent.provider import LLMProvider, LLMResponse
from bootstrap.app import AppRuntime, RuntimeFeatures
from core.roles.store import RoleStore
from desktop_bridge.runtime.service import ReloadableDesktopService

BOT_ID = 111
BOT_TOKEN = f"{BOT_ID}:secret"
SENDER_ID = 456
ROLE_ID = "mira"
REPLY = "今天的晚霞很好看"
INBOUND_TEXT = "晚上好"
MODEL_ID = "00000000-0000-4000-a000-000000000001"
# Long-poll pause of the fake getUpdates when nothing is queued.
_IDLE_POLL_S = 0.02
# Bound on the reply's round trip and on host shutdown. Telegram's outbound
# rate limiter alone spaces the live preview and the final reply by seconds.
_SETTLE_TIMEOUT_S = 15


class FakeBotApi:
    """Answers Bot API methods the way api.telegram.org would, recording calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        # sendMessage parameters by the message ID the platform assigned.
        self.sent: dict[str, dict[str, Any]] = {}
        self._updates: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._next_update_id = 1
        self._next_message_id = 900

    def deliver_private_text(self, text: str, *, message_id: int) -> None:
        """Queues a private message from the sender for the Bot's next poll."""
        sender: dict[str, Any] = {
            "id": SENDER_ID,
            "is_bot": False,
            "first_name": "Sender",
            "username": "sender",
        }
        self._updates.put_nowait(
            {
                "update_id": self._next_update_id,
                "message": {
                    "message_id": message_id,
                    "date": int(time.time()),
                    "chat": {
                        "id": SENDER_ID,
                        "type": "private",
                        "first_name": "Sender",
                    },
                    "from": sender,
                    "text": text,
                },
            }
        )
        self._next_update_id += 1

    async def do_request(
        self,
        url: str,
        method: str,
        request_data: RequestData | None = None,
        **_timeouts: object,
    ) -> tuple[int, bytes]:
        """Replaces the HTTP round trip with an in-memory Bot API answer."""
        api_method = url.rsplit("/", 1)[-1]
        params = dict(request_data.parameters) if request_data is not None else {}
        self.calls.append((api_method, params))
        result = await self._answer(api_method, params)
        return 200, json.dumps({"ok": True, "result": result}).encode()

    async def _answer(self, method: str, params: dict[str, Any]) -> object:
        if method == "getMe":
            return {
                "id": BOT_ID,
                "is_bot": True,
                "first_name": "Mira Bot",
                "username": "mira_bot",
            }
        if method == "getUpdates":
            return await self._poll(params)
        if method == "getUserProfilePhotos":
            return {"total_count": 0, "photos": []}
        if method == "getChat":
            return {
                "id": int(params["chat_id"]),
                "type": "private",
                "accent_color_id": 0,
                "max_reaction_count": 0,
            }
        if method == "sendMessage":
            self._next_message_id += 1
            self.sent[str(self._next_message_id)] = params
            return {
                "message_id": self._next_message_id,
                "date": int(time.time()),
                "chat": {"id": int(params["chat_id"]), "type": "private"},
                "text": params["text"],
            }
        if method in {
            "deleteWebhook",
            "setMyCommands",
            "sendChatAction",
            "deleteMessage",
        }:
            return True
        raise AssertionError(f"Unexpected Bot API call: {method} {params}")

    async def _poll(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Returns queued updates past the acknowledged offset, else waits briefly."""
        try:
            update = await asyncio.wait_for(self._updates.get(), _IDLE_POLL_S)
        except TimeoutError:
            return []
        if update["update_id"] < int(params.get("offset") or 0):
            return []
        return [update]


class FakeLLMProvider(LLMProvider):
    """The role's model: keeps the real request budgeting, answers without network."""

    async def chat(self, *args: Any, **kwargs: Any) -> LLMResponse:
        return LLMResponse(content=REPLY, finish_reason="stop")


_CONFIG = f"""\
[[llm.registrations]]
id = "{MODEL_ID}"
provider = "openai"
model = "fake"
api_key = "test-key"
base_url = "https://llm.example.invalid/v1"
model_context_window = 128000

[agent.maintenance]
memory_optimizer_enabled = false

[proactive]
enabled = false
profile = "quiet"
"""


@asynccontextmanager
async def _telegram_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, api: FakeBotApi
) -> AsyncGenerator[tuple[AppRuntime, ReloadableDesktopService], None]:
    """A full host with message channels on and only the Telegram plugin installed."""
    plugin_root = tmp_path / "plugin_dirs"
    _ = stage_plugin_package(plugin_directory("telegram"), plugin_root / "telegram")

    def resolve_plugin_dirs(_workspace: Path) -> list[Path]:
        return [plugin_root]

    monkeypatch.setattr("bootstrap.tools._resolve_plugin_dirs", resolve_plugin_dirs)

    async def do_request(
        _request: HTTPXRequest, url: str, method: str, **kwargs: Any
    ) -> tuple[int, bytes]:
        return await api.do_request(url, method, **kwargs)

    monkeypatch.setattr(HTTPXRequest, "do_request", do_request)
    monkeypatch.setattr("core.roles.model_runtime.LLMProvider", FakeLLMProvider)
    _ = RoleStore(tmp_path).create_role(
        role_id=ROLE_ID,
        name="Mira",
        system_prompt="你是 Mira。",
        runtime_config={"dialogue_model_registration_id": MODEL_ID},
    )
    config_path = tmp_path / "config.toml"
    _ = config_path.write_text(_CONFIG, encoding="utf-8")
    app = AppRuntime(
        load_config_text(_CONFIG),
        tmp_path,
        features=RuntimeFeatures(enable_message_channels=True, enable_proactive=False),
    )
    try:
        await app.start()
        core = app.core
        assert core is not None
        service = ReloadableDesktopService(
            app, config_path, core.role_runtime_registry.repository.store
        )
        try:
            yield app, service
        finally:
            await service.aclose()
    finally:
        # Shutdown drains accepted work; a reply stuck in the host must fail
        # the test instead of hanging it.
        async with asyncio.timeout(_SETTLE_TIMEOUT_S):
            await app.shutdown()


async def _wait_for_delivered_reply(app: AppRuntime) -> dict[str, Any]:
    """The role session's assistant message once the hub has marked its delivery."""
    sessions = app.session_manager
    assert sessions is not None
    session_key = sessions.role_session_key(ROLE_ID)
    async with asyncio.timeout(_SETTLE_TIMEOUT_S):
        while True:
            replies = [
                message
                for message in sessions.get_or_create(session_key).messages
                if message.get("role") == "assistant"
                and message.get("delivery_status") not in (None, "", "pending")
            ]
            if replies:
                return replies[-1]
            await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_private_message_is_answered_by_the_role_and_marked_sent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = FakeBotApi()
    async with _telegram_host(tmp_path, monkeypatch, api) as (app, service):
        saved = await plugin_bridge_request(
            service,
            "plugin.telegram.bot.save",
            {"role_id": ROLE_ID, "token": BOT_TOKEN},
        )
        assert saved.error is None, saved.error
        account_id = saved.payload["account_id"]

        api.deliver_private_text(INBOUND_TEXT, message_id=7)
        reply = await _wait_for_delivered_reply(app)

        # The hub recorded delivery on the committed reply, with the ID of
        # the platform message that carried the provider's reply to the
        # sender's chat, and the account that sent it.
        assert reply["content"] == REPLY
        assert reply["delivery_status"] == "sent"
        sent = api.sent[reply["external_message_id"]]
        assert int(sent["chat_id"]) == SENDER_ID
        assert REPLY in sent["text"]
        assert reply["metadata"]["via_account"]["platform_account_id"] == str(BOT_ID)
        # The inbound turn ran on the owning role's session, in the thread of
        # this account's private chat.
        sessions = app.session_manager
        assert sessions is not None
        history = sessions.get_or_create(sessions.role_session_key(ROLE_ID)).messages
        [user_turn] = [m for m in history if m.get("role") == "user"]
        assert INBOUND_TEXT in user_turn["content"]
        assert user_turn["metadata"]["account_id"] == account_id
        assert user_turn["metadata"]["thread_id"] == reply["metadata"]["thread_id"]
