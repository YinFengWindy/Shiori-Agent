"""Manual group edits and consolidation share conflict checks and rollback boundaries."""

from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from conversation.store import ConversationStore
from core.memory.external_writes import (
    ExternalLayerSnapshot,
    commit_external_layers,
    edit_group_environment,
)
from core.memory.group_environment import GroupEnvironment, GroupEnvironmentUpdate
from core.memory.member_profiles import MemberProfiles

_THREAD = "thread:mira:qq:g"
_OLD = datetime.fromisoformat("2020-01-02T03:04:05+08:00")
_EDITED = _OLD + timedelta(days=1)


def _environment(tmp_path: Path):
    environment = GroupEnvironment(
        tmp_path, ConversationStore(tmp_path / "sessions.db")
    )
    environment.apply(
        "mira",
        GroupEnvironmentUpdate(_THREAD, "群", "旧摘要", "旧笔记"),
        updated_at=_OLD,
    )
    return environment


@pytest.mark.parametrize("edit_summary", [False, True])
def test_note_write_failure_rolls_back_summary_and_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, edit_summary: bool
) -> None:
    environment = _environment(tmp_path)
    before = environment.read("mira", _THREAD)
    state_before = environment.conversation_store.get_thread_state(_THREAD)

    def fail_note(*_args: object) -> None:
        raise OSError("note write failed")

    monkeypatch.setattr(environment, "write_note", fail_note)
    with pytest.raises(OSError, match="note write failed"):
        _ = edit_group_environment(
            environment,
            "mira",
            _THREAD,
            group_note="新笔记",
            summary="新摘要" if edit_summary else None,
            label="新群名",
            updated_at=_EDITED,
        )

    assert environment.read("mira", _THREAD) == before
    assert environment.conversation_store.get_thread_state(_THREAD) == state_before


@pytest.mark.parametrize("previous_note", ["旧笔记", ""])
@pytest.mark.parametrize("edit_summary", [False, True])
def test_database_failure_after_note_save_restores_previous_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    previous_note: str,
    edit_summary: bool,
) -> None:
    environment = _environment(tmp_path)
    environment.write_note("mira", _THREAD, previous_note)
    before = environment.read("mira", _THREAD)
    transaction = environment.conversation_store.state_transaction

    @contextmanager
    def failed_commit():
        with transaction():
            yield
            raise OSError("commit failed")

    monkeypatch.setattr(
        environment.conversation_store, "state_transaction", failed_commit
    )
    with pytest.raises(OSError, match="commit failed"):
        _ = edit_group_environment(
            environment,
            "mira",
            _THREAD,
            group_note="新笔记",
            summary="新摘要" if edit_summary else None,
            label="群",
            updated_at=_EDITED,
        )

    assert environment.read("mira", _THREAD) == before
    assert environment.note_path("mira", _THREAD).exists() is bool(previous_note)


def test_failed_file_restore_reports_both_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = _environment(tmp_path)
    transaction = environment.conversation_store.state_transaction
    write_note = environment.write_note

    @contextmanager
    def failed_commit():
        with transaction():
            yield
            raise OSError("commit failed")

    def fail_restore(role_id: str, thread_id: str, note: str) -> None:
        if note == "旧笔记":
            raise OSError("restore failed")
        write_note(role_id, thread_id, note)

    monkeypatch.setattr(
        environment.conversation_store, "state_transaction", failed_commit
    )
    monkeypatch.setattr(environment, "write_note", fail_restore)
    with pytest.raises(ExceptionGroup, match="群笔记恢复失败") as caught:
        _ = edit_group_environment(
            environment,
            "mira",
            _THREAD,
            group_note="新笔记",
            summary="新摘要",
            label="群",
            updated_at=_EDITED,
        )
    assert [str(error) for error in caught.value.exceptions] == [
        "commit failed",
        "restore failed",
    ]
    assert environment.read("mira", _THREAD).recent_activity == "旧摘要"


@pytest.mark.parametrize("edited_field", ["group_note", "summary"])
def test_manual_edits_reject_stale_consolidation_and_allow_a_fresh_snapshot(
    tmp_path: Path, edited_field: str
) -> None:
    environment = _environment(tmp_path)
    before = environment.read("mira", _THREAD)
    _ = edit_group_environment(
        environment,
        "mira",
        _THREAD,
        **{edited_field: "用户修订"},
        label="群",
        updated_at=_EDITED,
    )
    after = environment.read("mira", _THREAD)
    update = GroupEnvironmentUpdate(_THREAD, "群", "整理摘要", "整理笔记")

    assert not commit_external_layers(
        environment,
        MemberProfiles(tmp_path),
        "mira",
        environment_updates=[update],
        member_updates=[],
        snapshot=ExternalLayerSnapshot(group_environments={_THREAD: before}),
        updated_at=_EDITED,
    )
    assert environment.read("mira", _THREAD) == after
    assert commit_external_layers(
        environment,
        MemberProfiles(tmp_path),
        "mira",
        environment_updates=[update],
        member_updates=[],
        snapshot=ExternalLayerSnapshot(group_environments={_THREAD: after}),
        updated_at=_EDITED,
    )
    assert environment.read("mira", _THREAD).recent_activity == "整理摘要"


def test_empty_summary_changed_and_cleared_still_invalidates_old_draft(
    tmp_path: Path,
) -> None:
    environment = GroupEnvironment(
        tmp_path, ConversationStore(tmp_path / "sessions.db")
    )
    before = environment.read("mira", _THREAD)
    _ = edit_group_environment(
        environment, "mira", _THREAD, summary="临时摘要", label="群", updated_at=_OLD
    )
    _ = edit_group_environment(
        environment, "mira", _THREAD, summary="", label="群", updated_at=_EDITED
    )
    cleared = environment.read("mira", _THREAD)

    assert cleared.recent_activity == before.recent_activity == ""
    assert cleared.summary_updated_at == _EDITED.isoformat()
    assert not commit_external_layers(
        environment,
        MemberProfiles(tmp_path),
        "mira",
        environment_updates=[GroupEnvironmentUpdate(_THREAD, "群", "旧草稿摘要", "")],
        member_updates=[],
        snapshot=ExternalLayerSnapshot(group_environments={_THREAD: before}),
        updated_at=_EDITED,
    )
    assert environment.read("mira", _THREAD) == cleared


@pytest.mark.parametrize("original_note", ["", "旧笔记"])
def test_note_changed_and_restored_rejects_old_draft_using_persistent_revision(
    tmp_path: Path, original_note: str
) -> None:
    environment = _environment(tmp_path)
    environment.write_note("mira", _THREAD, original_note)
    before = environment.read("mira", _THREAD)
    for note in ("临时修改", original_note):
        _ = edit_group_environment(
            environment,
            "mira",
            _THREAD,
            group_note=note,
            label="群",
            updated_at=_EDITED,
        )
    environment.conversation_store.close()
    # Reopening proves that deleting the note did not discard its edit revision.
    environment = GroupEnvironment(
        tmp_path, ConversationStore(tmp_path / "sessions.db")
    )
    after = environment.read("mira", _THREAD)
    assert after.group_note == before.group_note
    assert after.recent_activity == before.recent_activity
    assert after.summary_updated_at == before.summary_updated_at == _OLD.isoformat()
    assert after.edit_revision == before.edit_revision + 2
    update = GroupEnvironmentUpdate(_THREAD, "群", "", "整理新笔记")
    assert not commit_external_layers(
        environment,
        MemberProfiles(tmp_path),
        "mira",
        environment_updates=[update],
        member_updates=[],
        snapshot=ExternalLayerSnapshot(group_environments={_THREAD: before}),
        updated_at=_EDITED,
    )
    assert environment.read("mira", _THREAD) == after
    assert commit_external_layers(
        environment,
        MemberProfiles(tmp_path),
        "mira",
        environment_updates=[update],
        member_updates=[],
        snapshot=ExternalLayerSnapshot(group_environments={_THREAD: after}),
        updated_at=_EDITED,
    )
    assert environment.read_note("mira", _THREAD) == "整理新笔记"
    assert environment.read("mira", _THREAD).edit_revision == after.edit_revision


def test_unchanged_edit_and_reads_do_not_advance_revision(tmp_path: Path) -> None:
    environment = _environment(tmp_path)
    edited = edit_group_environment(
        environment,
        "mira",
        _THREAD,
        group_note="手动笔记",
        summary="手动摘要",
        label="群",
        updated_at=_EDITED,
    )
    state = environment.conversation_store.get_thread_state(_THREAD)
    assert edited.edit_revision == 1
    unchanged = edit_group_environment(
        environment,
        "mira",
        _THREAD,
        group_note=" 手动笔记 ",
        summary="手动摘要",
        label="群",
        updated_at=_EDITED + timedelta(days=1),
    )
    assert unchanged == edited == environment.read("mira", _THREAD)
    assert environment.conversation_store.get_thread_state(_THREAD) == state
