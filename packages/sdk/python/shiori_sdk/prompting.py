"""Markers identifying model-only context frames in history."""

SYSTEM_CONTEXT_FRAME_MARKER = '<system-reminder data-system-context-frame="true">'
SYSTEM_CONTEXT_FRAME_END = "</system-reminder>"
LEGACY_CONTEXT_FRAME_MARKER = "[SYSTEM_CONTEXT_FRAME]"


def is_context_frame(content: str) -> bool:
    """Identify current and legacy model-only context frames."""
    text = content.lstrip()
    return text.startswith("<system-reminder") or text.startswith(
        LEGACY_CONTEXT_FRAME_MARKER
    )
