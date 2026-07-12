from pathlib import Path

from agent.plugins.context import PluginKVStore
from agent.tool_hooks.types import HookOutcome
from plugins.novelai.auto_cg import AutoCgPolicy


def test_auto_cg_policy_enforces_cooldown_dedup_and_manual_bypass(
    tmp_path: Path,
) -> None:
    policy = AutoCgPolicy(PluginKVStore(tmp_path / ".kv.json"))
    session_key = "role:mira"
    policy.advance_turn(session_key)
    arguments = {
        "intent": "scene_cg",
        "scene_key": "  Rooftop  ",
        "prompt": "Mira on a rooftop",
        "negative_prompt": "blurry",
    }

    prepared = policy.guard(session_key, arguments)
    assert isinstance(prepared, dict)
    assert prepared["scene_key"] == "rooftop"
    assert "third-person view" in prepared["prompt"]
    assert "character visible in frame" in prepared["prompt"]
    assert prepared["negative_prompt"] == ("blurry, first-person view, pov, selfie")
    policy.record_success(session_key, arguments["scene_key"])
    for _ in range(8):
        policy.advance_turn(session_key)

    cooldown = policy.guard(
        session_key,
        {"intent": "scene_cg", "scene_key": "new scene"},
    )
    assert isinstance(cooldown, HookOutcome)
    assert cooldown.reason == "scene_cg_cooldown"
    assert policy.guard(session_key, {"intent": "user_requested"}) is None

    policy.advance_turn(session_key)
    next_scene = policy.guard(
        session_key,
        {
            "intent": "scene_cg",
            "scene_key": "new scene",
            "prompt": "Mira by the window",
        },
    )
    assert isinstance(next_scene, dict)
    assert next_scene["scene_key"] == "new scene"
    duplicate = policy.guard(
        session_key,
        {"intent": "scene_cg", "scene_key": "ROOFTOP"},
    )
    assert isinstance(duplicate, HookOutcome)
    assert duplicate.reason == "scene_cg_duplicate_scene"


def test_auto_cg_policy_requires_scene_key_and_isolates_sessions(
    tmp_path: Path,
) -> None:
    kv_store = PluginKVStore(tmp_path / ".kv.json")
    policy = AutoCgPolicy(kv_store)

    policy.advance_turn("role:mira")
    policy.advance_turn("role:mira")
    policy.advance_turn("role:yuki")

    sessions = kv_store.get("auto_cg_sessions")
    assert sessions["role:mira"] == {"turn": 2}
    assert sessions["role:yuki"] == {"turn": 1}
    missing_key = policy.guard("role:mira", {"intent": "scene_cg"})
    assert isinstance(missing_key, HookOutcome)
    assert missing_key.reason == "scene_cg_missing_scene_key"


def test_auto_cg_prompt_reports_current_cooldown(tmp_path: Path) -> None:
    policy = AutoCgPolicy(PluginKVStore(tmp_path / ".kv.json"))
    session_key = "role:mira"
    policy.advance_turn(session_key)
    policy.record_success(session_key, "rain")

    section = policy.build_prompt_section(session_key)

    assert "scene_cg" in section.content
    assert "角色本人必须清晰入镜" in section.content
    assert "禁止第一人称 POV" in section.content
    assert "还需等待至少 9 个用户回合" in section.content


def test_auto_cg_third_person_terms_are_idempotent(tmp_path: Path) -> None:
    policy = AutoCgPolicy(PluginKVStore(tmp_path / ".kv.json"))
    prepared = policy.guard(
        "role:mira",
        {
            "intent": "scene_cg",
            "scene_key": "garden",
            "prompt": "Mira in a garden, third-person view",
            "negative_prompt": "pov, selfie",
        },
    )

    assert isinstance(prepared, dict)
    assert prepared["prompt"].count("third-person view") == 1
    assert prepared["negative_prompt"].count("pov") == 1
    assert prepared["negative_prompt"].count("selfie") == 1
