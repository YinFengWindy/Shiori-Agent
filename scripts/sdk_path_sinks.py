"""File-system access points: where a relative path is resolved against the cwd.

A relative path is only cwd-rooted when it reaches an operation that touches
the file system; ordinary calls (``asset_path(...)``, ``ctx.resolve(...)``,
``storage.write(...)``) receive keys or plugin-relative names. Every sink is
listed here; the layout they must not name is ``scripts.sdk_repository_layout``.
"""

import ast

from scripts.sdk_path_values import PathValues, expand_arguments

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
