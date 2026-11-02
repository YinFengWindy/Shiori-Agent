"""Pure skill mention parsing shared by the host and skill-owning plugins."""

from collections.abc import Iterable
import re


def collect_skill_mentions(content: str, available_names: Iterable[str]) -> list[str]:
    """Return available ``$name`` mentions once, in their first appearance order.

    Names contain ASCII letters, digits, underscores and hyphens. Matching is
    case-sensitive; unknown names are ignored. This preserves the host's
    existing explicit-skill syntax without requiring a runtime service.
    """
    available = set(available_names)
    return list(
        dict.fromkeys(
            name
            for name in re.findall(r"\$([a-zA-Z0-9_-]+)", content)
            if name in available
        )
    )
