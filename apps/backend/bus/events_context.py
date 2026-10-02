"""Small context-control notifications, independent of ordinary chat turns."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ContextWindowChanged:
    """Refresh the owning context after manual work starts or releases its gate."""

    session_key: str
    context_key: str
    busy: bool = False
