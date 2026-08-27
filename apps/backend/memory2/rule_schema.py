from __future__ import annotations

import re
from typing import Any

_ASCII_ALIAS_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
_NEGATIVE_TOOL_PREFIXES = (
    "不能直接使用",
    "不能直接用",
    "不要直接使用",
    "不要直接用",
    "别直接使用",
    "别直接用",
    "不能先使用",
    "不能先用",
    "不要先使用",
    "不要先用",
    "别先使用",
    "别先用",
    "不能使用",
    "不能用",
    "不要使用",
    "不要用",
    "别使用",
    "别用",
    "禁止使用",
    "禁止用",
)
_POSITIVE_TOOL_PREFIXES = (
    "必须先使用",
    "必须先用",
    "必须使用",
    "必须用",
    "先使用",
    "先用",
    "优先使用",
    "优先用",
    "应先使用",
    "应先用",
    "应该使用",
    "应该用",
    "直接使用",
    "直接用",
)


def _extract_ascii_aliases(text: str) -> set[str]:
    aliases: set[str] = set()
    matches = list(_ASCII_ALIAS_PATTERN.finditer(text or ""))
    for match in matches:
        token = match.group(0).lower()
        if len(token) >= 2:
            aliases.add(token)
    for index in range(len(matches) - 1):
        left = matches[index]
        right = matches[index + 1]
        if text[left.end() : right.start()].strip() != "":
            continue
        phrase = f"{left.group(0).lower()}_{right.group(0).lower()}"
        if len(phrase) >= 2:
            aliases.add(phrase)
    return aliases


def build_procedure_rule_schema(
    summary: str,
    tool_requirement: str | None = None,
    steps: list[str] | None = None,
    rule_schema: dict[str, Any] | None = None,
) -> dict[str, list[str]]:
    required = set(_normalize_schema_list((rule_schema or {}).get("required_tools")))
    forbidden = set(_normalize_schema_list((rule_schema or {}).get("forbidden_tools")))
    mentioned = set(_normalize_schema_list((rule_schema or {}).get("mentioned_tools")))
    mentioned.update(_extract_ascii_aliases(summary))
    for step in steps or []:
        mentioned.update(_extract_ascii_aliases(step))
    if not required or not forbidden:
        inferred_required, inferred_forbidden = _infer_rule_constraints(summary, steps)
        if not required:
            required.update(inferred_required)
        if not forbidden:
            forbidden.update(inferred_forbidden)
    if tool_requirement:
        normalized = str(tool_requirement).strip().lower()
        if normalized:
            required.add(normalized)
            mentioned.add(normalized)
    forbidden.difference_update(required)
    return {
        "required_tools": sorted(required),
        "forbidden_tools": sorted(forbidden),
        "mentioned_tools": sorted(mentioned),
    }


def resolve_procedure_rule_schema(summary: str, extra: dict[str, Any] | None) -> dict[str, list[str]]:
    payload = extra or {}
    return build_procedure_rule_schema(
        summary=summary,
        tool_requirement=payload.get("tool_requirement"),
        steps=payload.get("steps") or [],
        rule_schema=payload.get("rule_schema"),
    )


def procedure_rules_conflict(
    new_schema: dict[str, list[str]],
    old_schema: dict[str, list[str]],
) -> bool:
    new_terms = _schema_terms(new_schema)
    old_terms = _schema_terms(old_schema)
    if not new_terms or not old_terms or not (new_terms & old_terms):
        return False
    new_required = set(new_schema.get("required_tools") or [])
    new_forbidden = set(new_schema.get("forbidden_tools") or [])
    old_required = set(old_schema.get("required_tools") or [])
    old_forbidden = set(old_schema.get("forbidden_tools") or [])
    return bool((new_required & old_forbidden) or (new_forbidden & old_required))


def _normalize_schema_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted(
        {
            str(item).strip().lower()
            for item in value
            if isinstance(item, str) and str(item).strip()
        }
    )


def _schema_terms(schema: dict[str, list[str]]) -> set[str]:
    return set(schema.get("mentioned_tools") or []) | set(
        schema.get("required_tools") or []
    ) | set(schema.get("forbidden_tools") or [])


def _infer_rule_constraints(
    summary: str,
    steps: list[str] | None,
) -> tuple[set[str], set[str]]:
    required: set[str] = set()
    forbidden: set[str] = set()
    for text in [summary, *(steps or [])]:
        for clause in re.split(r"[，。！？；;\n]", text or ""):
            for alias, prefix in _iter_alias_prefixes(clause):
                if any(prefix.endswith(cue) for cue in _NEGATIVE_TOOL_PREFIXES):
                    forbidden.add(alias)
                    continue
                if any(prefix.endswith(cue) for cue in _POSITIVE_TOOL_PREFIXES):
                    required.add(alias)
    return required, forbidden


def _iter_alias_prefixes(clause: str) -> list[tuple[str, str]]:
    matches = list(_ASCII_ALIAS_PATTERN.finditer(clause or ""))
    pairs: list[tuple[str, str]] = []
    index = 0
    while index < len(matches):
        match = matches[index]
        prefix = _normalize_prefix(clause[max(0, match.start() - 12) : match.start()])
        if index < len(matches) - 1:
            next_match = matches[index + 1]
            if clause[match.end() : next_match.start()].strip() == "":
                alias = f"{match.group(0).lower()}_{next_match.group(0).lower()}"
                pairs.append((alias, prefix))
                index += 2
                continue
        pairs.append((match.group(0).lower(), prefix))
        index += 1
    return pairs


def _normalize_prefix(text: str) -> str:
    return re.sub(r"\s+", "", text or "")
