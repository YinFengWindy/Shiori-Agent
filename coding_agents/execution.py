"""Coding Agent Adapter 的 Provider 路由与独立生命周期执行层。"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

from coding_agents.adapters import (
    AdapterError,
    AdapterEvent,
    AdapterResult,
    ClaudeAdapter,
    CodexAdapter,
    CodingAgentAdapter,
    PreparedRun,
    ProbeResult,
    ResumeSpec,
    RunHandle,
    TaskRunSpec,
)
from coding_agents.models import Provider

EventCallback = Callable[[AdapterEvent], Awaitable[None] | None]


class AdapterRegistry:
    """保存 Provider 到 Adapter 的显式一对一映射。"""

    def __init__(
        self,
        adapters: Mapping[Provider | str, CodingAgentAdapter] | None = None,
    ) -> None:
        self._adapters: dict[Provider, CodingAgentAdapter] = {}
        for provider, adapter in (adapters or {}).items():
            self.register(provider, adapter)

    @classmethod
    def with_defaults(cls) -> AdapterRegistry:
        """创建使用生产进程层的 Codex 与 Claude 注册表。"""
        return cls(
            {
                Provider.CODEX: CodexAdapter(),
                Provider.CLAUDE: ClaudeAdapter(),
            }
        )

    @property
    def providers(self) -> tuple[Provider, ...]:
        """稳定返回已注册的 Provider。"""
        return tuple(sorted(self._adapters, key=str))

    def register(
        self,
        provider: Provider | str,
        adapter: CodingAgentAdapter,
    ) -> None:
        """注册 Provider；重复注册直接失败。"""
        normalized = _parse_provider(provider)
        if normalized in self._adapters:
            raise ValueError(f"Provider 已注册：{normalized.value}")
        self._adapters[normalized] = adapter

    def get(self, provider: Provider | str) -> CodingAgentAdapter:
        """读取 Provider Adapter，不对缺失项静默回退。"""
        normalized = _parse_provider(provider)
        try:
            return self._adapters[normalized]
        except KeyError as exc:
            raise AdapterError(
                "provider_unavailable",
                f"Provider 未注册：{normalized.value}",
            ) from exc

    async def probe(self, provider: Provider | str) -> ProbeResult:
        """探测一个已注册 Provider 的 CLI 能力。"""
        return await self.get(provider).probe()

    async def probe_all(self) -> dict[Provider, ProbeResult]:
        """并行探测全部 Provider，返回稳定 Provider 键。"""
        providers = self.providers
        results = await asyncio.gather(
            *(self._adapters[provider].probe() for provider in providers)
        )
        return dict(zip(providers, results, strict=True))


@dataclass
class _ActiveRun:
    adapter: CodingAgentAdapter
    handle: RunHandle | None = None
    cancel_requested: bool = False


class AdapterExecutor:
    """执行 prepare、start、stream、collect_result 并管理活动 Run。"""

    def __init__(self, registry: AdapterRegistry) -> None:
        self.registry = registry
        self._active: dict[str, _ActiveRun] = {}
        self._active_lock = asyncio.Lock()

    async def execute(
        self,
        provider: Provider | str,
        spec: TaskRunSpec,
        *,
        on_event: EventCallback | None = None,
    ) -> AdapterResult:
        """执行一次完整 Adapter 生命周期并返回最终结果。"""
        adapter = self.registry.get(provider)
        prepared = adapter.prepare(spec)
        return await self._execute_prepared(adapter, prepared, on_event)

    async def resume(
        self,
        provider: Provider | str,
        spec: ResumeSpec,
        *,
        on_event: EventCallback | None = None,
    ) -> AdapterResult:
        """使用明确 session 恢复并执行同一套受管生命周期。"""
        adapter = self.registry.get(provider)
        prepared = adapter.resume(spec)
        return await self._execute_prepared(adapter, prepared, on_event)

    async def _execute_prepared(
        self,
        adapter: CodingAgentAdapter,
        prepared: PreparedRun,
        on_event: EventCallback | None,
    ) -> AdapterResult:
        spec = prepared.spec
        active = _ActiveRun(adapter=adapter)
        await self._reserve(spec.run_id, active)
        handle: RunHandle | None = None
        try:
            try:
                async with asyncio.timeout(spec.timeout_seconds):
                    handle = await adapter.start(prepared)
                    active.handle = handle
                    if active.cancel_requested:
                        await adapter.cancel(handle)
                        await self._emit_process_exit(handle, on_event)
                        return await self._collect(adapter, handle, on_event)
                    async for event in adapter.stream(handle):
                        await _emit(on_event, event)
                    return await self._collect(adapter, handle, on_event)
            except TimeoutError:
                if handle is None:
                    return await self._start_timeout(spec, on_event)
                return await self._timeout(adapter, handle, spec, on_event)
            except asyncio.CancelledError:
                if handle is not None:
                    await asyncio.shield(adapter.cancel(handle))
                raise
        finally:
            try:
                if handle is not None:
                    await asyncio.shield(adapter.cleanup(handle))
            finally:
                await self._release(spec.run_id, active)

    async def cancel(self, run_id: str) -> bool:
        """请求取消活动 Run；未知或已结束 Run 返回 False。"""
        async with self._active_lock:
            active = self._active.get(run_id)
            if active is None:
                return False
            active.cancel_requested = True
            handle = active.handle
        if handle is not None:
            await active.adapter.cancel(handle)
        return True

    async def probe(self, provider: Provider | str) -> ProbeResult:
        """通过注册表探测一个 Provider。"""
        return await self.registry.probe(provider)

    async def _reserve(self, run_id: str, active: _ActiveRun) -> None:
        async with self._active_lock:
            if run_id in self._active:
                raise AdapterError(
                    "process_start_failed",
                    f"Run 已在执行：{run_id}",
                )
            self._active[run_id] = active

    async def _release(self, run_id: str, active: _ActiveRun) -> None:
        async with self._active_lock:
            if self._active.get(run_id) is active:
                del self._active[run_id]

    async def _collect(
        self,
        adapter: CodingAgentAdapter,
        handle: RunHandle,
        on_event: EventCallback | None,
    ) -> AdapterResult:
        previous_event_count = len(handle.events)
        result = await adapter.collect_result(handle)
        for event in handle.events[previous_event_count:]:
            await _emit(on_event, event)
        return result

    async def _timeout(
        self,
        adapter: CodingAgentAdapter,
        handle: RunHandle,
        spec: TaskRunSpec,
        on_event: EventCallback | None,
    ) -> AdapterResult:
        await adapter.cancel(handle)
        handle.cancelled = False
        handle.timed_out = True
        handle.error_code = "process_timeout"
        handle.error_message = f"Adapter 生命周期超过 {spec.timeout_seconds:g} 秒"
        timeout_event = AdapterEvent(
            "adapter_error",
            {
                "code": handle.error_code,
                "message": handle.error_message,
            },
        )
        handle.events.append(timeout_event)
        await _emit(on_event, timeout_event)
        await self._emit_process_exit(handle, on_event)
        return await self._collect(adapter, handle, on_event)

    async def _emit_process_exit(
        self,
        handle: RunHandle,
        on_event: EventCallback | None,
    ) -> None:
        if any(event.event_type == "process_exited" for event in handle.events):
            return
        event = AdapterEvent(
            "process_exited",
            {
                "exit_code": handle.exit_code,
                "cancelled": handle.cancelled,
                "timed_out": handle.timed_out,
            },
        )
        handle.events.append(event)
        await _emit(on_event, event)

    async def _start_timeout(
        self,
        spec: TaskRunSpec,
        on_event: EventCallback | None,
    ) -> AdapterResult:
        message = f"Adapter 启动超过 {spec.timeout_seconds:g} 秒"
        await _emit(
            on_event,
            AdapterEvent(
                "adapter_error",
                {"code": "process_timeout", "message": message},
            ),
        )
        return AdapterResult(
            success=False,
            exit_code=-1,
            summary="",
            session_id=None,
            error_code="process_timeout",
            error_message=message,
        )


async def _emit(callback: EventCallback | None, event: AdapterEvent) -> None:
    if callback is None:
        return
    result = callback(event)
    if inspect.isawaitable(result):
        await result


def _parse_provider(provider: Provider | str) -> Provider:
    try:
        return Provider(provider)
    except ValueError as exc:
        raise AdapterError(
            "provider_unavailable",
            f"未知 Provider：{provider}",
        ) from exc
