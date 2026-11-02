"""Expose plugin-owned skills through the ordinary chat prompt extension."""

from dataclasses import replace
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring

from shiori_sdk.core.conversation import PromptRendering, TurnStarting
from shiori_sdk.prompting import PromptSectionRender
from shiori_sdk.skills import collect_skill_mentions

from .skill_resources import builtin_skills_dir, parse_skill_frontmatter


async def select_skill_mentions(
    event: TurnStarting, *, workspace: Path
) -> TurnStarting:
    """Activate mentioned package skills before the host prepares reasoning."""
    owned_names = (
        path.parent.name
        for path in builtin_skills_dir().glob("*/SKILL.md")
        if not (workspace / "skills" / path.parent.name / "SKILL.md").is_file()
    )
    mentions = collect_skill_mentions(event.content, owned_names)
    return replace(
        event, skill_names=tuple(dict.fromkeys((*event.skill_names, *mentions)))
    )


async def append_skill_prompt(
    event: PromptRendering, *, workspace: Path
) -> PromptRendering:
    """Contribute available and selected skills, leaving workspace overrides to core."""
    if event.minimal_request:
        return event
    catalog = Element("skills")
    selected: list[str] = []
    for path in sorted(builtin_skills_dir().glob("*/SKILL.md")):
        name = path.parent.name
        # The core already advertises and activates a workspace override.
        if (workspace / "skills" / name / "SKILL.md").is_file():
            continue
        content = path.read_text(encoding="utf-8")
        metadata = parse_skill_frontmatter(content)
        skill = SubElement(catalog, "skill", available="true", source="proactive")
        SubElement(skill, "name").text = name
        SubElement(skill, "description").text = str(metadata.get("description", name))
        SubElement(skill, "location").text = str(path)
        if name in event.skill_names:
            body = content.split("\n---", 1)[1].strip()
            selected.append(f"### Skill: {name}\n\n{body}")
    sections: list[PromptSectionRender] = []
    if len(catalog) and "skills_catalog" not in event.disabled_sections:
        sections.append(
            PromptSectionRender(
                name="skills_catalog",
                content=tostring(catalog, encoding="unicode"),
                is_static=True,
            )
        )
    if selected and "active_skills" not in event.disabled_sections:
        sections.append(
            PromptSectionRender(
                name="active_skills",
                content="# Active Skills\n\n" + "\n\n---\n\n".join(selected),
                is_static=False,
            )
        )
    return replace(
        event, system_sections_bottom=(*event.system_sections_bottom, *sections)
    )
