from pathlib import Path
from unittest.mock import Mock
from datetime import datetime, timezone
from conversation.context_scope import load_user_context_threads
from core.identity import IdentityChat, UserIdentityStore
from shiori_sdk.accounts.models import AccountRecord
from core.memory.markdown.recent_context_document import stamp_recent_context

import pytest
from core.memory.markdown.runtime import (
    MarkdownMemoryRuntime,
    MarkdownMemoryStore,
    resolve_markdown_store,
)


def test_resolve_markdown_store_requires_role_id(tmp_path: Path):
    with pytest.raises(ValueError, match="role_id required for markdown memory access"):
        resolve_markdown_store(workspace=tmp_path)


def test_unscoped_legacy_recent_document_is_not_automatically_rebound(tmp_path):
    runtime = MarkdownMemoryRuntime(
        store=MarkdownMemoryStore(tmp_path), maintenance=Mock(), workspace=tmp_path
    )
    role_store = runtime.resolve_store(role_id="mira")
    role_store.write_recent_context(
        "# 最近发生的事\n\n## 最近聊过的事\n- 最近持续关注：old private secret\n"
    )
    role_store.write_long_term("long-term memory")
    original = role_store.read_recent_context()
    assert runtime.read_recent_context(role_id="mira") == ""
    assert role_store.read_recent_context() == original
    assert "long-term memory" in runtime.read_long_term(role_id="mira")


def test_runtime_rejects_recent_context_after_unobserved_unbind_and_rebind(tmp_path):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    identities = UserIdentityStore(tmp_path, clock=lambda: now)
    account = AccountRecord(
        id="qq:101",
        plugin_id="qq",
        platform="qq",
        platform_account_id="101",
        config_ref="101",
        role_id="mira",
    )

    def bind():
        return identities.pair(
            identities.create_pairing_code().code,
            record=account,
            user_id="902",
            scope="platform",
            chat=IdentityChat(account.id, "qq", "902"),
        )

    identity = bind()
    assert identity is not None
    runtime = MarkdownMemoryRuntime(
        store=MarkdownMemoryStore(tmp_path), maintenance=Mock(), workspace=tmp_path
    )
    memory = runtime.resolve_store(role_id="mira")
    memory.write_recent_context(
        stamp_recent_context(
            "old private secret", load_user_context_threads(tmp_path, "mira")
        )
    )
    assert "old private secret" in runtime.read_recent_context(role_id="mira")
    identities.unbind(identity.id)
    now = datetime(2026, 1, 4, tzinfo=timezone.utc)
    assert bind()
    assert runtime.read_recent_context(role_id="mira") == ""
    assert "old private secret" in memory.read_recent_context()
