"""Stable failures owned by the Story bounded context."""

from __future__ import annotations


class StorySimulationError(RuntimeError):
    """Base class for Story domain failures."""

    code = "internal_error"


class StoryNotFoundError(StorySimulationError):
    """Raised when a Story or segment cannot be found."""

    code = "story_not_found"


class StoryRevisionConflictError(StorySimulationError):
    """Raised when a command uses an outdated Story revision."""

    code = "revision_conflict"


class StoryInvalidStateError(StorySimulationError):
    """Raised when a Story command is not valid for the current state."""

    code = "invalid_state"


class StoryTurnBusyError(StorySimulationError):
    """Raised when another Turn owns the active generation lane."""

    code = "turn_busy"


class StoryInvalidOutputError(StorySimulationError):
    """Raised when Director output cannot be validated as a Story draft."""

    code = "director_invalid_output"


class StoryProviderUnavailableError(StorySimulationError):
    """Raised when no configured provider can generate a Story draft."""

    code = "provider_not_configured"
