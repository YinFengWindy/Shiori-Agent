"""A failed native run must leave usable evidence before teardown or profile reuse."""

import asyncio
import json

import pytest

from scripts.browser_acceptance import BrowserAcceptanceEvidence


@pytest.mark.parametrize(
    "error", [RuntimeError("native failed"), asyncio.CancelledError()]
)
async def test_failed_attempt_is_saved_before_teardown(tmp_path, error):
    evidence = BrowserAcceptanceEvidence(tmp_path, {"runtime": "fixed"})

    async def fail():
        raise error

    with pytest.raises(type(error)) as raised:
        await evidence.run("open", fail, {"url": "http://127.0.0.1"})
    assert raised.value is error
    saved = json.loads((tmp_path / "acceptance.json").read_text(encoding="utf-8"))
    step = saved["steps"][0]
    assert step["operation"] == "open"
    assert step["status"] == (
        "cancelled" if isinstance(error, asyncio.CancelledError) else "failed"
    )
    assert step["elapsed_seconds"] >= 0
    assert step["error"]["type"] == type(error).__name__
    assert "raise error" in step["error"]["traceback"]

    async def cleanup():
        raise OSError("cleanup also failed")

    with pytest.raises(OSError):
        await evidence.run("unload", cleanup)
    evidence.finish(error)
    saved = json.loads((tmp_path / "acceptance.json").read_text(encoding="utf-8"))
    assert saved["error"]["type"] == type(error).__name__
    assert saved["steps"][0]["error"] == step["error"]
    assert saved["steps"][1]["error"]["message"] == "cleanup also failed"


async def test_profile_reuse_preserves_each_generation_log_and_identity(tmp_path):
    evidence = BrowserAcceptanceEvidence(tmp_path / "evidence", {})
    log = tmp_path / "daemon.log"

    async def start(session, pid):
        log.write_text(session, encoding="utf-8")
        evidence.daemon_started(session, pid, log)
        return "opened"

    await evidence.run("open", lambda: start("first", 1))
    evidence.daemon_stopped("first")
    await evidence.run("open", lambda: start("second", 2))
    evidence.daemon_stopped("second")
    evidence.finish()
    saved = json.loads(
        (tmp_path / "evidence" / "acceptance.json").read_text(encoding="utf-8")
    )
    assert [step["generation"] for step in saved["steps"]] == ["first", "second"]
    for generation in saved["generations"]:
        assert (evidence.directory / generation["log"]).read_text(
            encoding="utf-8"
        ) == generation["session"]
