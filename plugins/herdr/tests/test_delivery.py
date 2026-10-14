"""Actual Git checkout and validation commands prove delivery claims are checked."""

import asyncio
import json
import subprocess
import sys

import pytest

from shiori_sdk.testing.background_results import FakeBackgroundResultTarget
from shiori_sdk.testing.processes import FakeProcesses
from plugins.herdr.backend.cli import CommandError, HerdrCli
from plugins.herdr.backend.config import HerdrConfig
from plugins.herdr.backend.delivery import verify_delivery
from plugins.herdr.backend.models import CodingTask


class ValidationProcesses(FakeProcesses):
    """Run only Git and this test interpreter; external services remain controlled."""

    async def spawn(self, *command, **kwargs):
        assert command[0] in {"git", sys.executable}
        return await asyncio.create_subprocess_exec(*command, **kwargs), None


class GitHubFixtureCli(HerdrCli):
    """The remote PR is the single controlled boundary of delivery verification."""

    def __init__(self, directory, pr):
        super().__init__(HerdrConfig(), ValidationProcesses(), directory)
        self.pr = pr
        self.queries = []

    async def command(self, argv, **kwargs):
        if argv[0] == "gh":
            self.queries.append(argv)
            return json.dumps(self.pr)
        return await super().command(argv, **kwargs)


@pytest.fixture
def delivery(tmp_path):
    repository = tmp_path / "repository"
    repository.mkdir()

    def git(*args, cwd=repository):
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout.strip()

    git("init", "-b", "main")
    git("config", "user.name", "Fixture")
    git("config", "user.email", "fixture@example.test")
    (repository / "code.py").write_text("answer = 0\n", encoding="utf-8")
    (repository / "check.py").write_text(
        "from code import answer\nassert answer == 42\nprint('actual validation passed')\n",
        encoding="utf-8",
    )
    (repository / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "baseline")
    base = git("rev-parse", "HEAD")
    worktree = tmp_path / "worktree"
    branch = "codex/task-fixture"
    git("worktree", "add", "-b", branch, str(worktree), base)
    (worktree / "code.py").write_text("answer = 42\n", encoding="utf-8")
    git("add", ".", cwd=worktree)
    git("commit", "-m", "fix answer", cwd=worktree)
    head = git("rev-parse", "HEAD", cwd=worktree)
    directory = tmp_path / "artifacts"
    directory.mkdir()
    task = CodingTask(
        "task-1",
        "fix answer",
        repository,
        "codex",
        FakeBackgroundResultTarget(),
        directory,
        branch,
        "run-1",
        worktree=worktree,
        base_commit=base,
    )
    payload = {
        "task_id": task.id,
        "run_id": task.run_id,
        "status": "completed",
        "summary": "修复 answer",
        "validation": [{"argv": [sys.executable, "check.py"], "cwd": "."}],
        "pr_url": "https://github.com/owner/repo/pull/42",
        "blockers": [],
    }
    task.result_path.write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    cli = GitHubFixtureCli(
        tmp_path,
        {
            "url": payload["pr_url"],
            "isDraft": True,
            "state": "OPEN",
            "headRefName": branch,
            "headRefOid": head,
            "baseRefName": "main",
        },
    )
    return task, cli, payload


async def test_current_commit_tests_and_real_draft_are_required(delivery):
    task, cli, _ = delivery
    await verify_delivery(task, cli)
    assert task.pr_url.endswith("/42")
    assert "actual validation passed" in task.validation[0]["output"]
    assert cli.queries[0][3] == task.branch  # resolve PR in the task repository


@pytest.mark.parametrize(
    "change, message",
    [
        ({"run_id": "old-run"}, "当前任务回合"),
        ({"validation": []}, "实际验证"),
        ({"status": "blocked", "blockers": ["需要登录"]}, "需要登录"),
        ({"validation": [{"argv": [sys.executable, "check.py"], "cwd": ".."}]}, "超出"),
    ],
)
async def test_stale_missing_or_blocked_artifacts_are_rejected(
    delivery, change, message
):
    task, cli, payload = delivery
    task.result_path.write_text(json.dumps({**payload, **change}), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        await verify_delivery(task, cli)
    assert task.pr_url == ""


async def test_failed_actual_validation_cannot_be_overridden_by_agent_claim(delivery):
    task, cli, payload = delivery
    payload["validation"] = [
        {"argv": [sys.executable, "-c", "raise SystemExit(7)"], "cwd": "."}
    ]
    task.result_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CommandError):
        await verify_delivery(task, cli)
    assert task.pr_url == "" and not cli.queries


@pytest.mark.parametrize(
    "field,value", [("isDraft", False), ("headRefOid", "old-sha"), ("state", "MERGED")]
)
async def test_non_draft_or_wrong_head_or_merged_pr_is_rejected(delivery, field, value):
    task, cli, _ = delivery
    cli.pr[field] = value
    with pytest.raises(ValueError, match="Draft PR"):
        await verify_delivery(task, cli)
    assert task.pr_url == ""
