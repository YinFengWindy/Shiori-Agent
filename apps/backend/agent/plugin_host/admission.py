"""Preflight, trust admission and screened source ownership before activation."""

from pathlib import Path
from collections.abc import Callable, Mapping
from shiori_sdk.kernel import (
    Kernel,
    KernelState,
    PluginDiagnostic,
    PluginSpec,
    PackageContractError,
)
from agent.plugin_host.discovery import TrustCheck, refresh_dependency_admission
from agent.plugin_host.execution_identity import PluginExecutionIdentity
from agent.plugin_host.package_fingerprint import (
    PackageContent,
    inspect_package_content,
)
from agent.plugin_host.record import PluginRecord, find_record
from agent.plugin_host.settings import PluginGenerationSettings, plugin_enabled
from agent.plugin_host.state import PluginInstance, PluginView


class _ActivationRefused(Exception):
    """Spec setup refused an activation the host did not prepare."""


def runnable(record: PluginRecord, settings: PluginGenerationSettings) -> bool:
    """Admission and stored enablement decide whether a spec participates."""
    return record.admission is None and plugin_enabled(
        record.manifest, settings.plugin_configs.get(record.manifest.id, {})
    )


def running(kernel: Kernel, plugin_id: str) -> bool:
    """Whether the kernel currently holds ``plugin_id``'s scope."""
    try:
        _ = kernel.scope(plugin_id)
    except KeyError:
        return False
    return True


def wants_start(
    record: PluginRecord,
    settings: PluginGenerationSettings,
    kernel: Kernel,
    host_failures: Mapping[str, Exception],
) -> bool:
    """A selected plugin may start only without a scope or a restart barrier."""
    if not runnable(record, settings) or running(kernel, record.manifest.id):
        return False
    if record.candidate_id in host_failures:
        return False
    status = kernel.status(record.manifest.id)
    return (
        status is None
        or status.state is not KernelState.FAILED
        or not status.cleanup_errors
    )


def screen(
    record: PluginRecord,
    workspace: Path | None,
    screened: dict[str, PackageContent | None],
) -> bool:
    """Checks a package against its approval before it is planned runnable.

    A workspace package whose bytes no longer match the approved
    fingerprint, or whose id already executed other content in this
    desktop session, gets an ``UNTRUSTED`` / ``RESTART_REQUIRED``
    admission, so ``_spec`` makes it register-only. Otherwise the verified
    content is kept for the spec setup to import: the bytes checked here
    are the bytes executed, never read from disk again.
    """
    if record.source != "workspace":
        screened[record.candidate_id] = None
        return True
    try:
        content = inspect_package_content(record.plugin_dir)
        if content.fingerprint != record.fingerprint:
            raise PackageContractError(
                "trust_changed",
                "trust",
                "插件内容已变化，请重启并重新确认信任",
            )
        if workspace is not None:
            PluginExecutionIdentity(workspace).verify(
                record.manifest.id, record.plugin_dir, content.fingerprint
            )
    except PackageContractError as exc:
        execution_changed = exc.diagnostic.code == "executed_content_changed"
        record.admission = PluginDiagnostic(
            ("executed_content_changed" if execution_changed else "trust_changed"),
            "trust",
            "content",
            str(exc),
            str(record.plugin_dir),
            "RESTART_REQUIRED" if execution_changed else "UNTRUSTED",
        )
        return False
    screened[record.candidate_id] = content
    return True


def prepared(
    record: PluginRecord,
    *,
    records: Mapping[str, PluginRecord],
    instances: Mapping[str, PluginInstance],
    screened: dict[str, PackageContent | None],
    settings: PluginGenerationSettings,
) -> tuple[PluginInstance, PackageContent | None]:
    """Consume this activation's preflight exactly once, before importing any code."""
    plugin_id = record.manifest.id
    instance = instances.get(plugin_id)
    if instance is None or records.get(plugin_id) is not record:
        raise _ActivationRefused(f"插件 {plugin_id} 未经宿主准备，不能启动")
    if not runnable(record, settings):
        raise _ActivationRefused(f"插件 {plugin_id} 未通过准入或已禁用，不能启动")
    if record.candidate_id not in screened:
        raise _ActivationRefused(f"插件 {plugin_id} 的包内容未经复核，不能启动")
    return instance, screened.pop(record.candidate_id)


def record_execution(
    record: PluginRecord, content: PackageContent | None, workspace: Path | None
) -> None:
    """Persists the execution identity of screened workspace content, before import."""
    if content is not None and workspace is not None:
        PluginExecutionIdentity(workspace).record(
            record.manifest.id, record.plugin_dir, content.fingerprint
        )


def admit_trusted_candidate(
    records: list[PluginRecord],
    candidate: PluginRecord,
    *,
    retired: bool,
    view: Callable[[PluginRecord], PluginView],
    is_trusted: TrustCheck | None,
) -> list[PluginRecord]:
    """Validate and replace exactly one approved startup candidate."""
    previous = find_record(records, candidate.candidate_id)
    if (
        retired
        or previous is None
        or previous.source != "workspace"
        or previous.fingerprint != candidate.fingerprint
        or previous.manifest.id != candidate.manifest.id
        or candidate.admission is not None
    ):
        raise ValueError("插件候选已变化，请重新读取后确认")
    if view(previous).state not in {"UNTRUSTED", "BLOCKED", "DISABLED"}:
        raise ValueError("插件已执行或状态已变化，请重新读取后操作")
    records[records.index(previous)] = candidate
    if is_trusted is None:
        raise ValueError("插件信任检查不可用")
    refresh_dependency_admission(records, is_trusted)
    return records


async def plan_activations(
    wanted: list[PluginRecord],
    *,
    records: Mapping[str, PluginRecord],
    kernel: Kernel,
    settings: PluginGenerationSettings,
    host_failures: Mapping[str, Exception],
    screened: dict[str, PackageContent | None],
    make_spec: Callable[[PluginRecord], PluginSpec],
) -> dict[str, PluginRecord]:
    """Preflight selected plugins and newly released exclusions before any setup."""
    selected: dict[str, PluginRecord] = {}
    pending = list(wanted)
    while pending:
        record = pending.pop(0)
        if record.candidate_id in selected:
            continue
        selected[record.candidate_id] = record
        if runnable(record, settings):
            pending.extend(
                records[pid] for pid in record.manifest.dependencies if pid in records
            )
    for record in selected.values():
        if wants_start(record, settings, kernel, host_failures):
            screen(record, settings.workspace, screened)
    order = await kernel.plan(
        make_spec(record)
        for record in selected.values()
        if records.get(record.manifest.id) is record
    )
    while True:
        activate: dict[str, PluginRecord] = {}
        refused: list[PluginRecord] = []
        for plugin_id in order:
            record = records[plugin_id]
            if not wants_start(record, settings, kernel, host_failures):
                continue
            if (
                record.candidate_id not in selected
                and kernel.status(plugin_id) is not None
            ):
                continue
            if record.candidate_id not in screened and not screen(
                record, settings.workspace, screened
            ):
                refused.append(record)
            else:
                activate[plugin_id] = record
        if not refused:
            break
        order = await kernel.plan(make_spec(record) for record in refused)
    return activate


def fail_activation(
    record: PluginRecord | None,
    fingerprint: str,
    error: Exception,
    kernel: Kernel,
    host_failures: dict[str, Exception],
) -> None:
    """Remember a trusted first activation that never reached a running scope."""
    if (
        record is None
        or record.fingerprint != fingerprint
        or record.admission is not None
        or running(kernel, record.manifest.id)
    ):
        return
    status = kernel.status(record.manifest.id)
    if status is None or status.state is KernelState.STOPPED:
        host_failures[record.candidate_id] = error
