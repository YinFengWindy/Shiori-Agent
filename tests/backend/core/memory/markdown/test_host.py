"""``MARKDOWN_MEMORY`` on the host: the long-term commit and the role state."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.memory.markdown.host import HostMarkdownMemory
from core.memory.markdown.runtime import MarkdownMemoryStore
from core.roles import RoleStore


def _documents(workspace: Path):
    roles = RoleStore(workspace)
    roles.create_role(role_id="mira", name="mira", system_prompt="p")
    documents = HostMarkdownMemory(workspace, roles).role("mira")
    assert documents is not None
    return documents, roles, workspace / "roles" / "mira" / "memory"


def test_commit_backs_up_writes_archives_then_drops_the_snapshot(
    tmp_path: Path,
) -> None:
    documents, _roles, memory_dir = _documents(tmp_path)
    store = MarkdownMemoryStore(tmp_path / "roles" / "mira")
    store.write_long_term("# 我的长期记忆\n## 关于你\n- 旧")
    old = (memory_dir / "MEMORY.md").read_text(encoding="utf-8")
    store.append_pending_once("- [identity] 新", source_ref="t1")
    assert documents.snapshot_pending()

    documents.commit_long_term(
        "# 我的长期记忆\n## 关于你\n- 新", history_entry="归档: 新"
    )

    assert (memory_dir / "MEMORY.bak.md").read_text(encoding="utf-8") == old
    assert "- 新" in documents.read_long_term()
    history = (memory_dir / "HISTORY.md").read_text(encoding="utf-8")
    assert history.rstrip().endswith("归档: 新")
    assert not (memory_dir / "PENDING.snapshot.md").exists()
    assert documents.snapshot_pending() == ""


def test_a_failed_write_keeps_the_snapshot_for_the_next_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    documents, _roles, memory_dir = _documents(tmp_path)
    store = MarkdownMemoryStore(tmp_path / "roles" / "mira")
    store.append_pending_once("- [identity] 新", source_ref="t1")
    pending = documents.snapshot_pending()

    def fail(_self: object, _content: str) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(MarkdownMemoryStore, "write_long_term", fail)
    with pytest.raises(OSError):
        documents.commit_long_term("# 我的长期记忆", history_entry="归档: 新")
    monkeypatch.undo()

    assert (memory_dir / "PENDING.snapshot.md").exists()
    assert "归档: 新" not in (memory_dir / "HISTORY.md").read_text(encoding="utf-8")
    assert documents.snapshot_pending() == pending


def test_host_keys_are_hidden_and_refused(tmp_path: Path) -> None:
    documents, roles, _memory_dir = _documents(tmp_path)
    seed = {"status": "generated", "fingerprint": "f"}
    roles.update_role("mira", memory_init_state={"self_seed": seed})

    with pytest.raises(ValueError, match="reserved"):
        documents.write_state("self_seed", "garbage")
    with pytest.raises(ValueError, match="JSON"):
        documents.write_state("plugin_key", object())
    documents.write_state("plugin_key", 2)

    assert roles.get_role("mira").memory_init_state["self_seed"] == seed
    assert documents.read_state() == {"plugin_key": 2}
