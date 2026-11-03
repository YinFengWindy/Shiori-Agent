"""Built-in Drift skills keep their state out of the install tree."""

from datetime import datetime, timezone
from pathlib import Path

from plugins.proactive.backend.drift_state import DriftStateStore
from plugins.proactive.backend.skill_resources import builtin_skills_dir


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


def test_shipped_skills_allow_role_overrides_without_changing_installation(tmp_path):
    builtin = builtin_skills_dir()
    before = {path: path.read_bytes() for path in builtin.glob("*/SKILL.md")}
    store = DriftStateStore(
        tmp_path / "drift", builtin_skills_dir=builtin, include_builtin_skills=True
    )
    assert store.valid_skill_names() == {"meme-manage", "create-drift-skill"}
    override = store.skills_dir / "meme-manage" / "SKILL.md"
    override.parent.mkdir()
    override.write_text(
        "---\nname: meme-manage\ndescription: 角色自己维护的技能\n---\n",
        encoding="utf-8",
    )
    skills = {skill.name: skill for skill in store.scan_skills()}
    assert not skills["meme-manage"].builtin
    assert skills["meme-manage"].description == "角色自己维护的技能"
    assert skills["create-drift-skill"].builtin
    store.save_finish(
        skill_used="create-drift-skill",
        one_line="完成",
        next_action="等待",
        message_result="silent",
        note=None,
        now_utc=datetime.now(timezone.utc),
    )
    assert (store.skills_dir / "create-drift-skill" / "state.json").is_file()
    assert {path: path.read_bytes() for path in builtin.glob("*/SKILL.md")} == before
    assert not list(builtin.glob("*/state.json"))
