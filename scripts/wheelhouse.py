"""Dependency closures and offline installation from a private wheelhouse."""

from __future__ import annotations

import email.parser
import zipfile
from collections.abc import Callable, Iterable
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name, parse_wheel_filename

from scripts.commands import UV, run
from scripts.sdk_boundaries import is_local_distribution

RequirementSource = Callable[[str, str], Iterable[str] | None]


def requirement_closure(
    roots: Iterable[str], requirements_of: RequirementSource
) -> tuple[dict[str, list[Requirement]], list[tuple[str | None, Requirement]]]:
    """Walks requirements from ``roots`` for this interpreter.

    ``requirements_of(name, extra)`` returns the raw requirements a local
    package declares in that extra context ("" is the base context), or None
    when ``name`` is not a local package. Markers are evaluated with the active
    extra; a dependency only receives the extras requested on its own edge.

    Returns every requirement edge reaching each local package and the
    remaining external requirements with their declaring package (None for a
    root).
    """
    sources: dict[tuple[str, str], Iterable[str] | None] = {}

    def declared(name: str, extra: str) -> Iterable[str] | None:
        if (name, extra) not in sources:
            sources[name, extra] = requirements_of(name, extra)
        return sources[name, extra]

    local: dict[str, list[Requirement]] = {}
    external: list[tuple[str | None, Requirement]] = []
    visited: set[tuple[str, str]] = set()
    pending: list[tuple[Requirement, str, str | None]] = [
        (Requirement(root), "", None) for root in roots
    ]
    while pending:
        requirement, context, declarer = pending.pop()
        if requirement.marker and not requirement.marker.evaluate({"extra": context}):
            continue
        name = canonicalize_name(requirement.name)
        if declared(name, "") is None:
            external.append((declarer, requirement))
            continue
        local.setdefault(name, []).append(requirement)
        for extra in ("", *map(canonicalize_name, requirement.extras)):
            if (name, extra) in visited:
                continue
            visited.add((name, extra))
            pending.extend(
                (Requirement(dependency), extra, name)
                for dependency in declared(name, extra) or ()
            )
    return local, external


def requires_dist(wheel: Path) -> list[str]:
    """``Requires-Dist`` entries of a wheel, markers included."""
    with zipfile.ZipFile(wheel) as archive:
        metadata = next(
            name
            for name in archive.namelist()
            if name.count("/") == 1 and name.endswith(".dist-info/METADATA")
        )
        message = email.parser.Parser().parsestr(archive.read(metadata).decode())
    return message.get_all("Requires-Dist") or []


def wheelhouse_closure(
    local: Iterable[str], wheelhouse: Path
) -> tuple[list[Path], list[str]]:
    """Splits the closure of ``local`` into wheel files and third-party requirements.

    Each ``local`` requirement and every ``shiori-*`` dependency must be a wheel
    built into ``wheelhouse``; one missing there fails instead of falling back
    to a same-named index package.
    """
    available: dict[str, Path] = {
        parse_wheel_filename(wheel.name)[0]: wheel for wheel in wheelhouse.glob("*.whl")
    }
    reached, external = requirement_closure(
        local,
        lambda name, _extra: (
            requires_dist(available[name]) if name in available else None
        ),
    )
    third_party: set[str] = set()
    for declarer, requirement in external:
        if declarer is None or is_local_distribution(
            canonicalize_name(requirement.name)
        ):
            raise ValueError(
                f"{requirement} is not built in the local wheelhouse {wheelhouse}"
            )
        requirement.marker = None
        third_party.add(str(requirement))
    for name, requirements in reached.items():
        version = parse_wheel_filename(available[name].name)[1]
        for requirement in requirements:
            if not requirement.specifier.contains(version, prereleases=True):
                raise ValueError(
                    f"Local wheel {available[name].name} does not satisfy {requirement}"
                )
    return sorted(available[name] for name in reached), sorted(third_party)


def install_from_wheelhouse(
    python: Path,
    wheelhouse: Path,
    local: Iterable[str],
    *,
    third_party: Iterable[str] = (),
    cwd: Path,
    log: Path,
) -> None:
    """Installs local packages offline, then only third-party requirements.

    The local step uses exact wheel files with ``--no-index --no-deps``; the
    third-party step contains no ``shiori-*`` requirement, so neither the SDK
    nor a plugin can be resolved from a public index. ``uv pip check`` then
    proves the combined environment satisfies every declared requirement.
    """
    wheels, dependencies = wheelhouse_closure(local, wheelhouse)
    remote = sorted({*dependencies, *third_party})
    for requirement in remote:
        if is_local_distribution(canonicalize_name(Requirement(requirement).name)):
            raise ValueError(f"{requirement} must come from the local wheelhouse")
    command = [UV, "pip", "install", "--python", str(python)]
    run(
        [*command, "--no-index", "--no-deps", *map(str, wheels)],
        cwd=cwd,
        log=log.with_name(f"{log.stem}-local.log"),
    )
    if remote:
        run(
            [*command, *remote],
            cwd=cwd,
            log=log.with_name(f"{log.stem}-third-party.log"),
        )
    run(
        [UV, "pip", "check", "--python", str(python)],
        cwd=cwd,
        log=log.with_name(f"{log.stem}-check.log"),
    )
