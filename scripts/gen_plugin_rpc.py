"""Generate finite plugin RPC names from their actual Python registration sites."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any, NoReturn, cast

import yaml

ROOT = Path(__file__).resolve().parents[1]
_UNKNOWN = object()
_RPC = object()
_SERVICES = object()


class ContractError(ValueError):
    """A registration cannot be proved to have a finite method name."""


class Extractor:
    """Resolve literals, imported constants and finite registration tables, never code."""

    def __init__(self, root: Path):
        self.root = root
        self.cache: dict[Path, dict[str, object]] = {}
        self.registrations: list[dict[str, object]] = []
        self.services: list[dict[str, object]] = []
        self.extra: set[tuple[Path, str]] = set()

    def module_path(self, module: str, path: Path, level: int = 0) -> Path | None:
        if level:
            base = path.parent
            for _ in range(level - 1):
                base = base.parent
            choices = [base.joinpath(*module.split("."))]
        else:
            choices = [
                self.root.joinpath(*module.split(".")),
                self.root.joinpath("packages/sdk/python", *module.split(".")),
            ]
        for choice in choices:
            for candidate in (choice.with_suffix(".py"), choice / "__init__.py"):
                if candidate.is_file():
                    return candidate
        return None

    def globals(self, path: Path) -> dict[str, object]:
        if path in self.cache:
            return self.cache[path]
        env: dict[str, object] = {}
        self.cache[path] = env
        tree = ast.parse(path.read_text(encoding="utf-8"))
        # Imports under TYPE_CHECKING still give parameter identities.
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                target = self.module_path(node.module or "", path, node.level)
                for alias in node.names:
                    name = alias.asname or alias.name
                    if node.module == "shiori_sdk.core.services" and alias.name in {
                        "RPC",
                        "SERVICES",
                    }:
                        env[name] = _RPC if alias.name == "RPC" else _SERVICES
                    elif (
                        node.module == "shiori_sdk.rpc"
                        and alias.name == "RpcCapability"
                    ):
                        env[name] = _RPC
                    elif target:
                        env[name] = self.globals(target).get(alias.name, _UNKNOWN)
                        if (
                            alias.name.startswith("register_")
                            and node.module
                            and node.module.startswith("shiori_sdk.")
                        ):
                            self.extra.add((target, alias.name))
        for node in tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = self.value(node.value, env)
                for target in (
                    node.targets if isinstance(node, ast.Assign) else [node.target]
                ):
                    self.bind(target, value, env)
        return env

    def value(self, node: ast.AST | None, env: dict[str, object]) -> object:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, (ast.Name, ast.Attribute)):
            return env.get(ast.unparse(node), _UNKNOWN)
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            return tuple(self.value(item, env) for item in node.elts)
        if isinstance(node, ast.Dict):
            return {
                self.value(key, env): self.value(value, env)
                for key, value in zip(node.keys, node.values)
            }
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left, right = self.value(node.left, env), self.value(node.right, env)
            if isinstance(left, str) and isinstance(right, str):
                return left + right
        if isinstance(node, ast.JoinedStr):
            parts = [
                (
                    self.value(item.value, env)
                    if isinstance(item, ast.FormattedValue)
                    else self.value(item, env)
                )
                for item in node.values
            ]
            if all(isinstance(part, str) for part in parts):
                return "".join(cast(list[str], parts))
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Key"
            and node.args
        ):
            return ("key", self.value(node.args[0], env))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in {"require", "get"} and node.args:
                return self.value(node.args[0], env)
            if node.func.attr == "items":
                table = self.value(node.func.value, env)
                if isinstance(table, dict):
                    return tuple(table.items())
        return _UNKNOWN

    def bind(self, target: ast.AST, value: object, env: dict[str, object]) -> None:
        if isinstance(target, (ast.Name, ast.Attribute)):
            env[ast.unparse(target)] = value
        elif isinstance(target, (ast.Tuple, ast.List)):
            values = (
                value
                if isinstance(value, tuple) and len(value) == len(target.elts)
                else (_UNKNOWN,) * len(target.elts)
            )
            for child, item in zip(target.elts, values):
                self.bind(child, item, env)

    def fail(self, path: Path, node: ast.AST, message: str) -> NoReturn:
        raise ContractError(f"{path}:{node.lineno}: {message}")

    def walk(self, nodes: list[ast.stmt], env: dict[str, object], path: Path) -> None:
        for node in nodes:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = self.value(node.value, env)
                for target in (
                    node.targets if isinstance(node, ast.Assign) else [node.target]
                ):
                    self.bind(target, value, env)
            if isinstance(node, ast.ClassDef):
                class_env = dict(env)
                init = next(
                    (
                        item
                        for item in node.body
                        if isinstance(item, ast.FunctionDef) and item.name == "__init__"
                    ),
                    None,
                )
                if init:
                    self.function(init, class_env, path, propagate=True)
                for method in node.body:
                    if (
                        isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and method is not init
                    ):
                        self.function(method, class_env, path)
                continue
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.function(node, env, path)
                continue
            if isinstance(node, (ast.For, ast.AsyncFor)):
                values = self.value(node.iter, env)
                if isinstance(values, (tuple, dict)):
                    for item in values:
                        local = dict(env)
                        self.bind(node.target, item, local)
                        self.walk(node.body, local, path)
                else:
                    local = dict(env)
                    self.bind(node.target, _UNKNOWN, local)
                    self.walk(node.body, local, path)
                self.walk(node.orelse, dict(env), path)
                continue
            # Visit calls in this statement only, then descend into statement blocks.
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.stmt):
                    continue
                for call in ast.walk(child):
                    if (
                        isinstance(call, ast.Call)
                        and isinstance(call.func, ast.Attribute)
                        and call.func.attr == "register"
                    ):
                        owner = self.value(call.func.value, env)
                        if owner is _RPC:
                            name = (
                                self.value(call.args[0], env) if call.args else _UNKNOWN
                            )
                            if not isinstance(name, str):
                                self.fail(
                                    path,
                                    call,
                                    "RPC name is not a finite string/constant/table entry",
                                )
                            self.registrations.append(
                                {
                                    "name": name,
                                    "path": (
                                        path.relative_to(self.root).as_posix()
                                        if path.is_relative_to(self.root)
                                        else path.name
                                    ),
                                    "line": call.lineno,
                                }
                            )
                        elif owner is _SERVICES:
                            fields = {
                                kw.arg: self.value(kw.value, env)
                                for kw in call.keywords
                            }
                            service_id = (
                                self.value(call.args[0], env) if call.args else _UNKNOWN
                            )
                            methods = fields.get("methods")
                            if (
                                not isinstance(service_id, str)
                                or not isinstance(fields.get("contract"), str)
                                or not isinstance(methods, dict)
                                or not all(isinstance(key, str) for key in methods)
                            ):
                                self.fail(
                                    path,
                                    call,
                                    "Service id/contract/methods must be finite literals",
                                )
                            self.services.append(
                                {
                                    "service_id": service_id,
                                    "contract": fields["contract"],
                                    "methods": sorted(methods),
                                }
                            )
            for field in ("body", "orelse", "finalbody"):
                body = getattr(node, field, None)
                if isinstance(body, list):
                    self.walk(body, dict(env), path)
            for handler in getattr(node, "handlers", ()):
                self.walk(handler.body, dict(env), path)

    def function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        env: dict[str, object],
        path: Path,
        propagate: bool = False,
    ) -> None:
        local = dict(env)
        for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs):
            annotation = arg.annotation
            if isinstance(annotation, ast.Constant) and isinstance(
                annotation.value, str
            ):
                annotation = ast.parse(annotation.value, mode="eval").body
            local[arg.arg] = self.value(annotation, env)
        self.walk(node.body, local, path)
        if propagate:
            env.update(
                {key: value for key, value in local.items() if key.startswith("self.")}
            )


def plugin_contract(directory: Path, root: Path = ROOT) -> dict[str, Any]:
    """Read actual finite registration sites, including imported SDK registration helpers."""
    directory = directory.resolve()
    manifest = yaml.safe_load((directory / "manifest.yaml").read_text(encoding="utf-8"))
    extractor = Extractor(root)
    for path in sorted((directory / "backend").rglob("*.py")):
        extractor.walk(
            ast.parse(path.read_text(encoding="utf-8")).body,
            dict(extractor.globals(path)),
            path,
        )
    done: set[tuple[Path, str]] = set()
    while pending := extractor.extra - done:
        path, name = sorted(pending)[0]
        done.add((path, name))
        tree = ast.parse(path.read_text(encoding="utf-8"))
        function = next(
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name
        )
        extractor.function(function, extractor.globals(path), path)
    registrations = sorted(
        {
            (entry["name"], entry["path"], entry["line"])
            for entry in extractor.registrations
        }
    )
    methods = sorted({str(item[0]) for item in registrations})
    return {
        "plugin_id": manifest["id"],
        "dependencies": sorted(
            {
                *manifest.get("dependencies", []),
                *manifest.get("optional_dependencies", []),
            }
        ),
        "methods": methods,
        "registrations": [
            dict(zip(("name", "path", "line"), item)) for item in registrations
        ],
        "services": extractor.services,
    }


def generate(directory: Path, *, check: bool = False, root: Path = ROOT) -> None:
    """Write deterministic frontend constants and a receipt for real-setup comparison."""
    contract = plugin_contract(directory, root)
    entries = "\n".join(
        f"  {json.dumps(name)}: {json.dumps(name)}," for name in contract["methods"]
    )
    ts = (
        "// Generated from backend registrations by scripts.gen_plugin_rpc. Do not edit.\n"
        + "/** Backend method names owned by this plugin. */\n"
        + "export const rpcMethods = {\n"
        + entries
        + "\n} as const;\n\n/** A backend method accepted by this plugin. */\nexport type RpcMethod = typeof rpcMethods[keyof typeof rpcMethods];\n"
    )
    for name, content in [
        ("rpcMethods.generated.ts", ts),
        (
            "rpc-contract.generated.json",
            json.dumps(contract, indent=2, ensure_ascii=False) + "\n",
        ),
    ]:
        path = directory / name
        if check:
            if not path.is_file() or path.read_text(encoding="utf-8") != content:
                raise ContractError(
                    f"{path}: generated RPC contract is stale; run python -m scripts.gen_plugin_rpc"
                )
        else:
            path.write_text(content, encoding="utf-8")


def main() -> None:
    """Generate all repository plugins or one external/scaffold plugin directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    directories = (
        [args.plugin.resolve()]
        if args.plugin
        else [
            path.parent for path in sorted((ROOT / "plugins").glob("*/manifest.yaml"))
        ]
    )
    for directory in directories:
        generate(directory, check=args.check)
    print(
        f'{len(directories)} plugin RPC contracts {"checked" if args.check else "generated"}'
    )


if __name__ == "__main__":
    main()
