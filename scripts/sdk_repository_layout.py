"""The repository layout that SDK and plugin code must never name.

Single definition shared by the path rules and the literal scan.
"""

from pathlib import Path

HOST_BACKEND = Path(__file__).resolve().parents[1] / "apps/backend"
# Checkout directories that belong to this repository in any context.
REPOSITORY_DIRECTORIES = ("apps/backend", "apps/desktop", "tests/backend")


def repository_prefix(relative: str) -> bool:
    """Whether a checkout-relative path starts with a repository directory."""
    path = Path(relative).as_posix()
    return any(
        path == directory or path.startswith(directory + "/")
        for directory in REPOSITORY_DIRECTORIES
    )


def layout_literal(text: str) -> bool:
    """Whether a literal spells a repository path (an optional ``./`` allowed).

    Only a leading directory counts: URLs, prose and plugin-internal paths
    such as ``plugins/x/tests/backend/data.json`` merely contain the words.
    """
    normalized = text.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return any(
        normalized.startswith(directory + "/") for directory in REPOSITORY_DIRECTORIES
    )


def host_layout(relative: str, backend: Path = HOST_BACKEND) -> bool:
    """Whether a checkout-relative path names the actual host layout.

    Besides the repository directories, the path must exist below the host
    backend or name a file (it has a suffix) inside an existing host package
    directory: ``bootstrap/x.yaml`` matches while ``core/enabled`` does not.
    """
    if repository_prefix(relative):
        return True
    parts = Path(relative).parts
    if not parts or parts[0] in {".", ".."}:
        return False
    target = backend.joinpath(*parts)
    return target.exists() or (
        target.parent != backend and target.parent.is_dir() and bool(target.suffix)
    )
