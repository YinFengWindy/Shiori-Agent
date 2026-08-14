from pathlib import Path

from core.memory.markdown_schema import (
    DOCUMENT_DEFAULTS,
    ensure_memory_documents,
    normalize_memory_document,
    pending_body,
)


def test_new_role_documents_use_canonical_schema(tmp_path: Path) -> None:
    ensure_memory_documents(tmp_path)

    for filename, default in DOCUMENT_DEFAULTS.items():
        assert (tmp_path / filename).read_text(encoding="utf-8") == default


def test_legacy_role_documents_migrate_without_conflicting_headings(
    tmp_path: Path,
) -> None:
    (tmp_path / "SELF.md").write_text("# 角色背景\n\n沉稳、克制。\n", encoding="utf-8")
    (tmp_path / "MEMORY.md").write_text(
        "# 关系基线\n\n来源: user_edited\n\n我们正在逐步建立信任。\n",
        encoding="utf-8",
    )
    (tmp_path / "HISTORY.md").write_text(
        "# 角色背景修订\n\n旧背景已被替换。\n", encoding="utf-8"
    )

    ensure_memory_documents(tmp_path)

    self_text = (tmp_path / "SELF.md").read_text(encoding="utf-8")
    memory_text = (tmp_path / "MEMORY.md").read_text(encoding="utf-8")
    history_text = (tmp_path / "HISTORY.md").read_text(encoding="utf-8")
    assert self_text.startswith("# 我是谁")
    assert "沉稳、克制。" in self_text
    assert "我们正在逐步建立信任。" in self_text
    assert "# 角色背景" not in self_text
    assert memory_text == DOCUMENT_DEFAULTS["MEMORY.md"]
    assert history_text.startswith("# 我们的共同经历")
    assert "# 角色背景修订" not in history_text

    snapshot = {
        filename: (tmp_path / filename).read_text(encoding="utf-8")
        for filename in DOCUMENT_DEFAULTS
    }
    ensure_memory_documents(tmp_path)
    assert snapshot == {
        filename: (tmp_path / filename).read_text(encoding="utf-8")
        for filename in DOCUMENT_DEFAULTS
    }


def test_legacy_recent_context_and_pending_are_read_compatibly() -> None:
    recent = normalize_memory_document(
        "RECENT_CONTEXT.md",
        "# Recent Context\n\n## Compression\n- old\n## Recent Turns\n- turn\n",
    )
    assert "## 最近聊过的事" in recent
    assert "## 最近的对话" in recent
    pending = "# 待整理的记忆\n- [preference] 保持简洁\n"
    assert pending_body(pending) == "- [preference] 保持简洁"


def test_legacy_prose_migrates_to_role_relative_perspective() -> None:
    migrated = normalize_memory_document(
        "MEMORY.md",
        (
            "# 用户长期记忆\n\n"
            "## 用户事实\n"
            "- 用户购买了咖啡，用户觉得味道不错。\n"
            "- 助手建议下次尝试拿铁。\n"
            "[assistant] 机器标记中的助手原文保持不变\n"
        ),
    )

    assert "你购买了咖啡，你觉得味道不错。" in migrated
    assert "我建议下次尝试拿铁。" in migrated
    assert "[assistant] 机器标记中的助手原文保持不变" in migrated
    assert "用户购买了" not in migrated
