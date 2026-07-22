"""Stable domain failures for persistent world simulation."""


class WorldSimulationError(RuntimeError):
    """Base class for world simulation failures exposed at application boundaries."""


class WorldNotFoundError(WorldSimulationError):
    """Raised when a requested world does not exist."""


class StaleWorldRevisionError(WorldSimulationError):
    """Raised when a command was based on an outdated world revision."""


class DecisionBarrierBlockedError(WorldSimulationError):
    """Raised when a command would advance beyond an unresolved barrier."""


class HistoricalConflictError(WorldSimulationError):
    """Raised when a historical backfill can affect settled causal history."""


class InvalidWorldProposalError(WorldSimulationError):
    """Raised when a proposed beat violates a world invariant."""


class InvalidRunTransitionError(WorldSimulationError):
    """Raised when a world run is moved through an invalid state transition."""
