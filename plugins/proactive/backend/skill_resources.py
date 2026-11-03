"""Read-only skill files shipped with the proactive package."""

from pathlib import Path
import re


def builtin_skills_dir() -> Path:
    """The package resource directory in source, wheels and frozen bundles."""
    return Path(__file__).resolve().parent.parent / "skills"


def parse_skill_frontmatter(content: str) -> dict[str, str | list[str]]:
    """Read the flat metadata and MCP list used by Drift skills."""
    if not content.startswith("---"):
        return {}
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if match is None:
        return {}
    metadata: dict[str, str | list[str]] = {}
    lines = match.group(1).split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if ":" not in line:
            i += 1
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if value:
            metadata[key] = value
            i += 1
            continue
        # value 为空 → 检查后续行是否为 YAML 列表项 (  - item)
        list_items: list[str] = []
        j = i + 1
        while j < len(lines):
            item_match = re.match(r"^\s+-\s+(.+)", lines[j])
            if item_match is None:
                break
            list_items.append(item_match.group(1).strip().strip("\"'"))
            j += 1
        if list_items:
            metadata[key] = list_items
            i = j
        else:
            metadata[key] = value
            i += 1
    return metadata
