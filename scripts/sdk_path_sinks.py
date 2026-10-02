"""File-system access points and the host layout a relative path must not name.

A relative path is only cwd-rooted when it reaches an operation that touches
the file system; ordinary calls (``asset_path(...)``, ``ctx.resolve(...)``,
``storage.write(...)``) receive keys or plugin-relative names. Every sink is
listed here.
"""

import ast
from pathlib import Path

from scripts.sdk_path_values import PathValues, expand_arguments

HOST_BACKEND = Path(__file__).resolve().parents[1] / "apps/backend"

# Qualified function -> positional arguments that are file-system paths.
FUNCTION_SINKS: dict[str, tuple[int, ...]] = {
    "builtins.open": (0,),
    "io.open": (0,),
    "os.open": (0,),
    "os.listdir": (0,),
    "os.scandir": (0,),
    "os.stat": (0,),
    "os.lstat": (0,),
    "os.walk": (0,),
    "os.chdir": (0,),
    "os.access": (0,),
    "os.remove": (0,),
    "os.unlink": (0,),
    "os.rmdir": (0,),
    "os.removedirs": (0,),
    "os.mkdir": (0,),
    "os.makedirs": (0,),
    "os.rename": (0, 1),
    "os.replace": (0, 1),
    "os.path.exists": (0,),
    "os.path.isfile": (0,),
    "os.path.isdir": (0,),
    "os.path.getsize": (0,),
    "os.path.getmtime": (0,),
    "glob.glob": (0,),
    "glob.iglob": (0,),
    "sys.path.insert": (1,),
    "sys.path.append": (0,),
}
# Every positional argument of these modules' functions is a path.
MODULE_SINKS = ("shutil.",)
# Methods of a concrete pathlib path that access the file system.
PATH_METHOD_SINKS = frozenset(
    {
        "open",
        "read_text",
        "read_bytes",
        "write_text",
        "write_bytes",
        "iterdir",
        "glob",
        "rglob",
        "exists",
        "is_file",
        "is_dir",
        "stat",
        "lstat",
        "mkdir",
        "rmdir",
        "unlink",
        "touch",
        "rename",
        "replace",
    }
)


def sink_paths(call: ast.Call, values: PathValues) -> list[ast.expr]:
    """Expressions whose value ``call`` uses as a file-system path."""
    qualified = values.qualified(call.func)
    if qualified and qualified.startswith("ntpath."):
        qualified = "os.path." + qualified.removeprefix("ntpath.")
    args = expand_arguments(call.args) or []
    if qualified in FUNCTION_SINKS:
        return [args[index] for index in FUNCTION_SINKS[qualified] if index < len(args)]
    if qualified and qualified.startswith(MODULE_SINKS):
        return args
    if (
        isinstance(call.func, ast.Attribute)
        and call.func.attr in PATH_METHOD_SINKS
        and values.evaluate(call.func.value)
    ):
        return [call.func.value]
    return []


def repository_prefix(relative: str) -> bool:
    """``apps/`` and ``tests/backend/`` belong to this checkout in any context."""
    parts = Path(relative).parts
    return bool(parts) and (parts[0] == "apps" or parts[:2] == ("tests", "backend"))


def host_layout(relative: str, backend: Path = HOST_BACKEND) -> bool:
    """Whether a checkout-relative path names the actual host layout.

    Besides the repository prefixes, the path must exist below the host backend
    or name a file (it has a suffix) inside an existing host package directory:
    ``bootstrap/x.yaml`` matches while ``core/enabled`` does not.
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
