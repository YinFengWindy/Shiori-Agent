"""Initial tool visibility shared by speaking and idle-context request rendering."""

from agent.tools.registry import ToolRegistry
from .helpers import turn_tool_names


def initial_tool_order(
    tools: ToolRegistry,
    history_names: list[str],
    *,
    disabled: set[str],
    external_restricted: bool,
) -> list[str]:
    """Keep always-on tools first, followed by the persisted discovery order."""
    always_on = tools.get_always_on_names()
    allowed = set(
        turn_tool_names(
            tools,
            always_on | set(history_names),
            disabled=disabled,
            external_restricted=external_restricted,
        )
        or []
    )
    ordered = tools.get_registered_order(always_on & allowed)
    seen = set(ordered)
    for name in history_names:
        if name in allowed and name not in seen:
            ordered.append(name)
            seen.add(name)
    return ordered
