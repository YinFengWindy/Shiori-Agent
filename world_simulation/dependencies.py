"""Causal dependency sets used to validate historical backfill."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DependencySet:
    """Facts, state keys, and cognition sources read or written by an event."""

    read_facts: frozenset[str] = frozenset()
    read_state: frozenset[str] = frozenset()
    cognition_sources: frozenset[str] = frozenset()
    write_facts: frozenset[str] = frozenset()
    write_state: frozenset[str] = frozenset()
    write_cognition: frozenset[str] = frozenset()

    def conflicts_with(self, later: "DependencySet") -> set[str]:
        """Return keys whose backfilled writes could change a later event's basis."""

        return set(
            (self.write_facts & (later.read_facts | later.write_facts))
            | (self.write_state & (later.read_state | later.write_state))
            | (self.write_cognition & later.cognition_sources)
        )

    def to_dict(self) -> dict[str, list[str]]:
        """Serialize dependency keys deterministically."""

        return {
            name: sorted(getattr(self, name))
            for name in (
                "read_facts",
                "read_state",
                "cognition_sources",
                "write_facts",
                "write_state",
                "write_cognition",
            )
        }

    @classmethod
    def from_dict(cls, value: dict[str, object] | None) -> "DependencySet":
        """Restore dependency keys from a persisted mapping."""

        payload = value or {}
        names = (
            "read_facts",
            "read_state",
            "cognition_sources",
            "write_facts",
            "write_state",
            "write_cognition",
        )
        parsed = {}
        for name in names:
            raw = payload.get(name, [])
            values = raw if isinstance(raw, (list, tuple, set, frozenset)) else ()
            parsed[name] = frozenset(str(item) for item in values)
        return cls(**parsed)
