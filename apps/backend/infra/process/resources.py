"""Process-owned plugin resources, part of the PROCESSES provider.

``ProcessResourceOwner`` outlives any one plugin generation: attachments are
per generation, ``publish`` switches the active generation, and ``retain``
keeps resources across an in-generation reload. ``HostProcesses`` (native
processes) lives beside this module; bootstrap provides both under PROCESSES.
"""

import asyncio
from collections.abc import Callable, Iterable
from contextvars import Context
from typing import cast

from shiori_sdk.process_resources import ProcessResource

from shiori_sdk.kernel import Scope

from agent.plugin_host.core_keys import PluginBinding


class ProcessResourceOwner:
    """Own resources independently of provider/channel configuration lifetimes."""

    def __init__(self) -> None:
        self._resources: dict[tuple[str, str], ProcessResource] = {}
        self._attachments: dict[tuple[str, str], set[str]] = {}
        self._active: str | None = None
        # (generation, plugin) pairs whose attachments are being replaced
        # within the generation; their resources outlive the detaching instance.
        self._retained: set[tuple[str, str]] = set()
        self._closing: set[asyncio.Task[None]] = set()
        self._errors: list[BaseException] = []
        self._closed = False

    def for_plugin(self, generation: str, plugin: str, effects: Scope):
        """Return one generation's private attachment and register its rollback."""
        scope = _Attachment(self, generation, plugin, effects)
        _ = effects.effect(scope.close, "process_resources")
        return scope

    def retain(self, generation: str, plugins: Iterable[str]) -> "ResourceRetention":
        """Keeps these plugins' resources while their instances reload in-generation.

        Until ``release()``, an attachment that closes detaches without
        retiring the shared resource, so the replacing instance re-acquires
        the same object.
        """
        held = frozenset((generation, plugin) for plugin in plugins)
        self._retained |= held
        return ResourceRetention(self, held)

    def publish(self, generation: str) -> None:
        """Switch active attachments without waiting for long-running plugin work."""
        if self._closed:
            raise RuntimeError("进程资源已关闭")
        previous = self._active
        self._active = generation
        for key, attachments in tuple(self._attachments.items()):
            if generation not in attachments and previous in attachments:
                self._retire(key)

    def _retire(self, key: tuple[str, str]) -> asyncio.Task[None]:
        resource = self._resources.pop(key)
        self._attachments.pop(key)
        task = asyncio.create_task(resource.close(), context=Context())
        self._closing.add(task)

        def finished(done: asyncio.Task[None]) -> None:
            self._closing.discard(done)
            if not done.cancelled() and (error := done.exception()) is not None:
                self._errors.append(error)

        task.add_done_callback(finished)
        return task

    async def close(self) -> None:
        """Stop monitors before runtimes/providers close and retain cleanup failures."""
        self._closed = True
        self._active = None
        for key in tuple(self._resources):
            self._retire(key)
        await self.drain()

    async def _await_retired(
        self, pending: list[asyncio.Task[None]]
    ) -> list[BaseException]:
        """Waits for retirements and claims their failures for the caller."""
        results = await asyncio.gather(*pending, return_exceptions=True)
        errors = [result for result in results if isinstance(result, BaseException)]
        for error in errors:
            if error in self._errors:
                self._errors.remove(error)
        return errors

    async def end_retention(
        self, held: frozenset[tuple[str, str]]
    ) -> list[BaseException]:
        """Implements ``ResourceRetention.release`` for the pairs it held."""
        self._retained -= held
        plugins = {plugin for _generation, plugin in held}
        pending = [
            self._retire(key)
            for key, attachments in tuple(self._attachments.items())
            if key[0] in plugins and not attachments
        ]
        return await self._await_retired(pending) if pending else []

    async def drain(self) -> None:
        """Finish publication cleanup and report errors at the responsible boundary."""
        await asyncio.gather(*tuple(self._closing), return_exceptions=True)
        if self._errors:
            errors, self._errors = self._errors, []
            raise BaseExceptionGroup("插件进程资源清理失败", errors)


class _Attachment:
    def __init__(
        self,
        owner: ProcessResourceOwner,
        generation: str,
        plugin: str,
        effects: Scope,
    ):
        self.owner, self.generation, self.plugin = owner, generation, plugin
        self.effects = effects
        self.keys: set[tuple[str, str]] = set()
        self.closed = False

    @property
    def active(self) -> bool:
        return (
            not self.closed
            and self.effects.active
            and self.owner._active == self.generation
            and not self.owner._closed
        )

    def acquire[T: ProcessResource](self, key: str, factory: Callable[[], T]) -> T:
        if self.closed or self.owner._closed:
            raise RuntimeError("插件进程资源附件已关闭")
        if not key.strip():
            raise ValueError("进程资源契约 key 不能为空")
        identity = (self.plugin, key)
        if identity not in self.owner._resources:
            self.owner._resources[identity] = factory()
            self.owner._attachments[identity] = set()
        self.owner._attachments[identity].add(self.generation)
        self.keys.add(identity)
        # The versioned key is the explicit structural contract across import
        # namespaces; Python class identity intentionally changes on reload.
        return cast(T, self.owner._resources[identity])

    async def close(self) -> None:
        self.closed = True
        pending = []
        for key in self.keys:
            attachments = self.owner._attachments.get(key)
            if attachments is None:
                continue
            attachments.discard(self.generation)
            if (self.generation, self.plugin) in self.owner._retained:
                continue
            if not attachments or self.owner._active == self.generation:
                pending.append(self.owner._retire(key))
        # Only teardown of the active attachment or unreferenced provisional
        # objects reaches close; retiring an old generation leaves active work.
        if pending:
            errors = await self.owner._await_retired(pending)
            if errors:
                raise BaseExceptionGroup("插件进程资源附件清理失败", errors)


class ResourceRetention:
    """One in-generation reload's hold on its plugins' process resources."""

    def __init__(
        self, owner: ProcessResourceOwner, held: frozenset[tuple[str, str]]
    ) -> None:
        self._owner = owner
        self._held = held

    async def release(self) -> list[BaseException]:
        """Ends the hold; retires resources no new instance re-acquired.

        Returns their close failures to the caller instead of leaving them
        for the next ``drain()``.
        """
        return await self._owner.end_retention(self._held)


class PluginProcessResourceAttachments:
    """The ``host.process_resources`` core service over the process-level owner.

    Each plugin gets this generation's private attachment (keyed by the kernel
    namespace), released with the plugin scope.
    """

    def __init__(self, owner: ProcessResourceOwner) -> None:
        self._owner = owner

    def for_plugin(self, binding: PluginBinding) -> "_Attachment":
        """The attachment of the plugin ``binding`` describes, in its generation."""
        return self._owner.for_plugin(
            binding.namespace, binding.plugin_id, binding.scope
        )
