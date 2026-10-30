"""One role's optimization through ``MARKDOWN_MEMORY`` and the role's chat model."""

from __future__ import annotations

from shiori_sdk.testing.models import FakeModels

from plugins.memory_optimizer.backend.optimizer import (
    LAST_OPTIMIZED_STATE_KEY,
    SELF_RULES_VERSION,
    SELF_RULES_VERSION_STATE_KEY,
    MemoryOptimizer,
)

from .conftest import FakeMarkdownMemory, FakeRoleDocuments, HeldProvider, Snapshot


async def test_one_run_merges_pending_rewrites_self_and_records_state() -> None:
    memory = FakeMarkdownMemory()
    documents = memory.roles["mira"] = FakeRoleDocuments(
        long_term="# 我的长期记忆\n- 旧",
        self_text="# 我是谁\n## 我们的关系\n- 你住在上海",
        pending="- [identity] 你在读研",
    )
    provider = HeldProvider("# 我的长期记忆\n- 你在读研", "# 我是谁\n- 新")
    models = FakeModels()
    models.snapshots["mira", "chat"] = Snapshot(provider, "role-chat")

    await MemoryOptimizer(step_delay_seconds=0).optimize(memory, models, "mira")

    assert models.activations == [("mira", "chat")]
    assert provider.requests == ["role-chat", "role-chat"]
    assert documents.long_term == "# 我的长期记忆\n- 你在读研"
    assert documents.backups == 1
    assert documents.history == [
        "[memory_optimizer] PENDING 归档:\n- [identity] 你在读研"
    ]
    assert (documents.pending, documents.snapshot) == ("", None)
    assert documents.self_text == "# 我是谁\n- 新"
    # SELF.md had never been rewritten under the current rules: this run did it.
    assert documents.state[SELF_RULES_VERSION_STATE_KEY] == SELF_RULES_VERSION
    assert LAST_OPTIMIZED_STATE_KEY in documents.state
