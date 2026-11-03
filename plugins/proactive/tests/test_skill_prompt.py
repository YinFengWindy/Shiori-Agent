"""Plugin skill discovery and explicit activation respect core overrides and budgets."""

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from xml.etree.ElementTree import fromstring

from shiori_sdk.core.conversation import PromptRendering

from plugins.proactive.backend.skill_prompt import append_skill_prompt
from plugins.proactive.backend.skill_resources import parse_skill_frontmatter


def _request():
    return PromptRendering(
        session_key="role:mira",
        channel="desktop",
        chat_id="role:mira",
        content="hello",
        media=(),
        timestamp=datetime.now(timezone.utc),
        context_scope=None,
        history=(),
        skill_names=("meme-manage",),
        retrieved_memory_block="",
        disabled_sections=frozenset(),
        turn_injection_prompt="",
        session_metadata={},
        supports_reply_sequence=False,
        minimal_request=False,
    )


async def test_advertised_files_are_readable_and_workspace_overrides_belong_to_core(
    tmp_path,
):
    event = _request()
    result = await append_skill_prompt(event, workspace=tmp_path)
    catalog = fromstring(result.system_sections_bottom[0].content)
    advertised = {}
    for item in catalog:
        location = item.findtext("location")
        assert location is not None
        advertised[item.findtext("name")] = Path(location)
    assert set(advertised) == {"meme-manage", "create-drift-skill"}
    for name, path in advertised.items():
        assert parse_skill_frontmatter(path.read_text(encoding="utf-8"))["name"] == name
    assert [section.name for section in result.system_sections_bottom] == [
        "skills_catalog",
        "active_skills",
    ]
    override = tmp_path / "skills" / "meme-manage" / "SKILL.md"
    override.parent.mkdir(parents=True)
    override.write_text("workspace version", encoding="utf-8")
    result = await append_skill_prompt(event, workspace=tmp_path)
    # Core owns both advertising and activating this override, so no duplicate
    # plugin body may obscure it; the other packaged skill remains discoverable.
    [section] = result.system_sections_bottom
    assert section.name == "skills_catalog"
    assert [item.findtext("name") for item in fromstring(section.content)] == [
        "create-drift-skill"
    ]


async def test_skill_budget_trimming_does_not_drop_explicit_activation(tmp_path):
    event = replace(_request(), disabled_sections=frozenset({"skills_catalog"}))
    result = await append_skill_prompt(event, workspace=tmp_path)
    assert [section.name for section in result.system_sections_bottom] == [
        "active_skills"
    ]
    event = replace(
        event, disabled_sections=frozenset({"skills_catalog", "active_skills"})
    )
    assert (
        await append_skill_prompt(event, workspace=tmp_path)
    ).system_sections_bottom == ()
    minimal = replace(_request(), minimal_request=True)
    assert await append_skill_prompt(minimal, workspace=tmp_path) == minimal
