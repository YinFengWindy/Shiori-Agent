from unittest.mock import AsyncMock

import pytest

from memory2.store import MemoryStore2
from plugins.default_memory.engine.lifecycle import DefaultMemoryEngine


@pytest.mark.asyncio
async def test_post_response_extraction_receives_current_role_memory(tmp_path) -> None:
    store = MemoryStore2(tmp_path / "memory2.db")
    try:
        store.upsert_item(
            "preference",
            "你喜欢拿铁",
            embedding=None,
            extra={"role_id": "mira"},
        )
        store.upsert_item(
            "preference",
            "你喜欢红茶",
            embedding=None,
            extra={"role_id": "atlas"},
        )
        engine = object.__new__(DefaultMemoryEngine)
        engine._v2_store = store
        engine._extract_implicit_long_term = AsyncMock(return_value=None)

        await engine._extract_and_save_post_response(
            user_msg="我还喜欢摩卡",
            assistant_response="记住了",
            source_ref="role:mira@post_response",
            channel="desktop",
            chat_id="role:mira",
            role_id="mira",
        )

        existing_profile = engine._extract_implicit_long_term.await_args.kwargs[
            "existing_profile"
        ]
        assert "你喜欢拿铁" in existing_profile
        assert "你喜欢红茶" not in existing_profile
    finally:
        store.close()
