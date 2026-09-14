"""Version comparison for the deliberately small Runtime Contract range grammar."""

from __future__ import annotations

import re
from dataclasses import dataclass

_SEMVER = re.compile(
    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
)


@dataclass(frozen=True)
class SemVer:
    """A SemVer 2.0 value, including prerelease precedence and ignored build data."""

    release: tuple[int, int, int]
    prerelease: tuple[str, ...] = ()

    @classmethod
    def parse(cls, value: str) -> SemVer:
        """Reject non-SemVer values rather than normalizing ambiguous versions."""
        match = _SEMVER.fullmatch(value)
        if match is None:
            raise ValueError(f"Invalid SemVer: {value}")
        pre = tuple(match[4].split(".")) if match[4] else ()
        if any(x.isdigit() and len(x) > 1 and x.startswith("0") for x in pre):
            raise ValueError(f"Invalid SemVer prerelease: {value}")
        return cls((int(match[1]), int(match[2]), int(match[3])), pre)

    def compare(self, other: SemVer) -> int:
        """Return -1, 0 or 1 according to SemVer precedence."""
        if self.release != other.release:
            return (self.release > other.release) - (self.release < other.release)
        if not self.prerelease or not other.prerelease:
            return bool(other.prerelease) - bool(self.prerelease)
        for left, right in zip(self.prerelease, other.prerelease):
            if left == right:
                continue
            if left.isdigit() and right.isdigit():
                return (int(left) > int(right)) - (int(left) < int(right))
            if left.isdigit() != right.isdigit():
                return -1 if left.isdigit() else 1
            return (left > right) - (left < right)
        return (len(self.prerelease) > len(other.prerelease)) - (
            len(self.prerelease) < len(other.prerelease)
        )


def satisfies(version: str, expression: str) -> bool:
    """Match space-separated =, >, >=, <, <= comparators (logical AND only).

    Bare exact SemVer is accepted. npm caret/tilde/OR/wildcards are not.
    Prerelease hosts require a comparator for the same prerelease release tuple.
    """
    current = SemVer.parse(version)
    clauses = expression.split()
    if not clauses:
        raise ValueError("Version range must not be empty")
    results: list[bool] = []
    allows_pre = not current.prerelease
    for clause in clauses:
        match = re.fullmatch(r"(>=|<=|>|<|=)?(.+)", clause)
        if match is None:
            raise ValueError(f"Invalid version comparator: {clause}")
        target = SemVer.parse(match[2])
        allows_pre |= bool(target.prerelease and target.release == current.release)
        order = current.compare(target)
        results.append(
            {
                "=": order == 0,
                ">": order > 0,
                ">=": order >= 0,
                "<": order < 0,
                "<=": order <= 0,
            }[match[1] or "="]
        )
    return allows_pre and all(results)
