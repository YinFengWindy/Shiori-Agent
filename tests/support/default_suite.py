"""Default host pytest selection for critical host contracts.

``pytest`` with no path arguments collects this set from ``tests/backend``.
``pytest --also <path>`` keeps this set and also collects those host paths.
Everything else under ``tests/backend`` is marked ``extended``.
``scripts/select_tests.py`` decides when CI passes ``--also`` or ``--extended``.

Not on this path:

- ``plugins/*/tests`` — ``scripts.verify_plugin_tests`` and
  ``pytest plugins/<id>/tests``
- ``packages/sdk/tests`` — ``scripts.verify_sdk`` and
  ``pytest packages/sdk/tests``
- Remaining host scenarios (reasoner loop, proactive agent loop, shell
  and message tools, role and memory writes) — ``pytest --extended``

An explicit path such as ``pytest tests/backend/agent/core/passive_turn/test_reasoning_loop.py``
still collects that file. The Windows CI job passes explicit paths and is
not filtered by this list.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

# Whole directories whose tests are host-owned and small enough to keep.
DEFAULT_DIRECTORIES: tuple[str, ...] = (
    "tests/backend/shiori_host_testing",
    "tests/backend/infra",
    "tests/backend/bus",
    "tests/backend/agent/lifecycle",
    "tests/backend/agent/looping",
    "tests/backend/agent/turns",
    "tests/backend/agent/policies",
    "tests/backend/agent/background",
    "tests/backend/agent/account_delivery",
)

# Files kept when the rest of their directory is extended.
DEFAULT_FILES: frozenset[str] = frozenset(
    {
        "tests/backend/test_main.py",
        "tests/backend/test_spawn_completion_flow.py",
        "tests/backend/agent/plugin_host/test_kernel.py",
        "tests/backend/agent/plugin_host/test_kernel_reload.py",
        "tests/backend/agent/plugin_host/test_package_contract.py",
        "tests/backend/conversation/test_external_turns.py",
        "tests/backend/bootstrap/test_wiring.py",
        "tests/backend/bootstrap/test_app.py",
        "tests/backend/bootstrap/runtime/test_reload.py",
        "tests/backend/bootstrap/runtime/test_shutdown.py",
        "tests/backend/bootstrap/runtime/test_generations.py",
        "tests/backend/bootstrap/runtime/test_dispatcher.py",
        "tests/backend/bootstrap/test_channel_host.py",
        "tests/backend/session/manager/test_undo.py",
        "tests/backend/session/test_manager.py",
        "tests/backend/session/test_turns.py",
        "tests/backend/core/memory/test_runtime.py",
        "tests/backend/core/memory/test_external_writes.py",
        "tests/backend/core/memory/markdown/test_consolidation.py",
        "tests/backend/core/roles/test_store.py",
        "tests/backend/core/roles/test_role_runtime.py",
        "tests/backend/core/roles/test_services.py",
        "tests/backend/desktop_bridge/test_request_dispatcher.py",
        "tests/backend/desktop_bridge/test_request_router.py",
        "tests/backend/desktop_bridge/test_method_policy.py",
        "tests/backend/agent/core/passive_turn/test_pipeline.py",
        "tests/backend/agent/core/passive_turn/test_empty_reply.py",
        "tests/backend/agent/core/passive_turn/test_reply_recovery.py",
        "tests/backend/agent/core/passive_turn/test_compaction.py",
        "tests/backend/agent/core/test_turn_pipelines.py",
        # P3 golden trace（维护者 2026-10-23 确认）与 core-only 冒烟（§5.3），#902。
        "tests/backend/agent/core/test_turn_golden_trace.py",
        # P6b 主动回合 golden trace，#907 PR0：proactive 搬进插件期间每次 CI
        # 都要守住的行为基线。
        "tests/backend/agent/core/test_proactive_turn_golden_trace.py",
        "tests/backend/agent/core/test_response_parser.py",
        "tests/backend/agent/core/test_safety_retry.py",
        "tests/backend/agent/core/test_p7_commit.py",
        "tests/backend/agent/proactive_host/test_delivery.py",
        "tests/backend/agent/tools/test_registry.py",
        # 工具执行器（ToolCalling / 核心链后校验 / ToolCalled）的宿主契约，#902。
        "tests/backend/agent/tools/test_execution.py",
        "tests/backend/agent/tools/test_turn_scope.py",
        "tests/backend/agent/tools/test_message_push.py",
        "tests/backend/scripts/test_check_sdk_imports.py",
        "tests/backend/scripts/test_isolation_probe.py",
        "tests/backend/scripts/test_verify_plugin_tests.py",
        "tests/backend/scripts/test_sdk_boundaries.py",
        "tests/backend/scripts/test_sdk_path_sinks.py",
        "tests/backend/scripts/test_commands.py",
        "tests/backend/scripts/test_default_suite.py",
        "tests/backend/scripts/test_select_tests.py",
    }
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def is_default_test(rel: str) -> bool:
    """Return whether a repo-relative test path is on the default CI path."""
    if rel in DEFAULT_FILES:
        return True
    return any(rel.startswith(directory + "/") for directory in DEFAULT_DIRECTORIES)


def directory_has_default_test(rel: str) -> bool:
    """Return whether a directory contains at least one default-path test."""
    prefix = f"{rel}/" if rel else ""
    if any(
        directory == rel
        or directory.startswith(prefix)
        or rel.startswith(directory + "/")
        for directory in DEFAULT_DIRECTORIES
    ):
        return True
    return any(path.startswith(prefix) for path in DEFAULT_FILES)


def path_covered_by_also(rel: str, extras: Iterable[str]) -> bool:
    """Return whether ``rel`` is an ``--also`` path, inside one, or a parent of one.

    Parents must stay visible. Ignoring a directory skips the whole tree and
    would hide an extended file requested underneath it.
    """
    for extra in extras:
        normalized = extra.replace("\\", "/").strip("/")
        if not normalized:
            continue
        if rel == normalized or rel.startswith(normalized + "/"):
            return True
        if normalized.startswith(rel + "/"):
            return True
    return False


def should_ignore_collect(rel: str, *, is_dir: bool) -> bool:
    """Ignore extended host tests. Never ignore conftest or helper modules."""
    if is_dir:
        return not directory_has_default_test(rel)
    name = rel.rsplit("/", 1)[-1]
    if not (name.startswith("test_") and name.endswith(".py")):
        return False
    return not is_default_test(rel)


def selection_is_default_root(args: list[str], *, cwd: Path, root: Path) -> bool:
    """True when pytest was started on the whole host tree (or with no args)."""
    if not args:
        return True
    for arg in args:
        path = Path(arg)
        if not path.is_absolute():
            path = cwd / path
        try:
            relative = path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            return False
        if relative != "tests/backend":
            return False
    return True
