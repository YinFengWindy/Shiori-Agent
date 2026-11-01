"""Built-in Drift skills keep their state out of the install tree."""

from datetime import datetime, timezone
from pathlib import Path

from plugins.proactive.backend.drift_state import DriftStateStore


def test_builtin_skill_state_is_written_under_the_workspace(tmp_path: Path) -> None:
    install = tmp_path / "install" / "meme-manage"
    install.mkdir(parents=True)
    (install / "SKILL.md").write_text(
        "---\nname: meme-manage\ndescription: 管理表情\n---\n",
        encoding="utf-8",
    )
    drift = tmp_path / "drift"
    store = DriftStateStore(
        drift,
        builtin_skills_dir=tmp_path / "install",
        include_builtin_skills=True,
        builtin_skill_names={"meme-manage"},
    )
    store.save_finish(
        skill_used="meme-manage",
        one_line="做了",
        next_action="继续",
        message_result="silent",
        note=None,
        now_utc=datetime.now(timezone.utc),
    )
    assert not (install / "state.json").exists()
    state_dir = store.skill_dir_for("meme-manage")
    assert state_dir == drift / "skills" / "meme-manage"
    assert (state_dir / "state.json").is_file()
    [skill] = store.scan_skills()
    assert (skill.name, skill.run_count, skill.builtin) == ("meme-manage", 1, True)
