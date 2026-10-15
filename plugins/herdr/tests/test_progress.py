"""Only complete current-run structured reports advance visible activity."""

import json

import pytest

from plugins.herdr.backend.models import CodingTask
from plugins.herdr.backend.progress import read_progress
from shiori_sdk.testing.background_results import FakeBackgroundResultTarget


@pytest.fixture
def task(tmp_path):
    return CodingTask(
        "task-a",
        "implement",
        tmp_path,
        "codex",
        FakeBackgroundResultTarget(),
        tmp_path,
        "codex/task",
        "run-current",
    )


def report(task, sequence, stage, **extra):
    return (
        json.dumps(
            {
                "task_id": task.id,
                "run_id": task.run_id,
                "sequence": sequence,
                "stage": stage,
                "detail": "实际活动",
                **extra,
            },
            ensure_ascii=False,
        )
        + "\n"
    )


def test_stage_regression_is_real_progress_but_old_run_duplicates_and_reordering_are_not(
    task,
):
    task.progress_path.write_text(
        report(task, 1, "analysis")
        + report(task, 2, "validation")
        + report(task, 3, "implementation"),
        encoding="utf-8",
    )
    assert read_progress(task)
    assert task.stage == "implementation" and len(task.progress_events) == 3
    task.progress_path.write_text(
        report(task, 2, "pull_request")
        + report(task, 3, "validation")
        + report(task, 99, "pull_request", run_id="previous-run"),
        encoding="utf-8",
    )
    assert not read_progress(task)
    assert task.stage == "implementation" and len(task.progress_events) == 3


def test_prompt_echo_partial_json_and_foreign_task_cannot_advance(task):
    task.progress_path.write_text(
        report(task, 1, "analysis", task_id="another-task")
        + "Read the progress instructions\n"
        + report(task, 2, "implementation").rstrip("\n"),
        encoding="utf-8",
    )
    assert not read_progress(task)
    assert task.stage == "" and task.progress_events == []
    assert task.progress_notice


def test_history_and_input_size_are_bounded(task):
    task.progress_path.write_text(
        "".join(report(task, i, "implementation") for i in range(1, 151)),
        encoding="utf-8",
    )
    assert read_progress(task)
    assert len(task.progress_events) == 100 and task.progress_sequence == 150
    task.progress_path.write_text("x" * 262145, encoding="utf-8")
    assert not read_progress(task)
    assert task.progress_sequence == 150 and "上限" in task.progress_notice


def test_unreadable_progress_remains_diagnostic_and_preserves_last_stage(
    task, monkeypatch
):
    task.stage = "implementation"

    def denied(*_args, **_kwargs):
        raise PermissionError("agent is replacing the file")

    monkeypatch.setattr(type(task.progress_path), "open", denied)
    assert not read_progress(task)
    assert task.stage == "implementation" and "暂不可读" in task.progress_notice
