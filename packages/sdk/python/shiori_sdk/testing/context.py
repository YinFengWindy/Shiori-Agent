"""A pure contract setup context with explicitly granted fake capabilities."""

import inspect
from pathlib import Path
from typing import cast

from shiori_sdk.core import services
from shiori_sdk.kernel import Context, Kernel, Key, PluginSpec, Scope, Veto
from shiori_sdk.kernel.events import OnHandler, WatchHandler
from shiori_sdk.runtime import (
    CapabilityNotGranted,
    Dispose,
    require_known_capabilities,
)
from .events import FakeEvents


class FakePluginContext:
    """Records setup effects and exports without instantiating any host services.

    ``capabilities`` are the grants, normally a manifest's declaration (see the
    ``sdk_context`` fixture); names unknown to the host are rejected like the host
    does. Only ``events`` has a fake here; other declared names are recorded in
    ``granted`` for specialized fakes.

    The kernel members (``provide`` / ``require`` / ``get``, ``on`` / ``watch``
    / ``emit``) run on a real ``Kernel``: ``kernel`` (a fresh one by default)
    with ``inject`` / ``optional_inject`` / ``provides`` as the manifest
    declares them. ``package_dir`` reads those three lists from that package's
    ``manifest.yaml`` instead. Provide core stubs on ``kernel`` before calling
    setup.

    ``require`` / ``get`` reject a key the declaration lacks with the kernel's
    ``undeclared_key`` error, as the host does. A declared former-capability
    key (``shiori_sdk.core.services``) that ``kernel`` has no provider for is
    served by the fake the test set as the attribute of that name
    (``ctx.kv = ...``; ``session_store`` is ``ctx.sessions``): the host
    provides those keys itself.
    """

    def __init__(
        self,
        plugin_id: str = "test_plugin",
        plugin_dir: Path = Path("."),
        *,
        capabilities: tuple[str, ...] = ("events",),
        kernel: Kernel | None = None,
        inject: tuple[str, ...] = (),
        optional_inject: tuple[str, ...] = (),
        provides: tuple[str, ...] = (),
        package_dir: Path | None = None,
    ) -> None:
        require_known_capabilities(capabilities, f"FakePluginContext({plugin_id})")
        if package_dir is not None:
            if inject or optional_inject or provides:
                raise ValueError(
                    "package_dir 与 inject/optional_inject/provides 二选一"
                )
            inject, optional_inject, provides = read_manifest_keys(package_dir)
        self.plugin_id = plugin_id
        self.plugin_dir = plugin_dir
        self.granted = tuple(sorted(set(capabilities)))
        self.exported: object | None = None
        self._events = FakeEvents()
        self._effects: list[tuple[str, Dispose]] = []
        self._closed = False
        self.kernel = kernel if kernel is not None else Kernel()
        self._scope = Scope(plugin_id)
        self._inject = frozenset(inject)
        self._optional_inject = frozenset(optional_inject)
        spec = PluginSpec(
            plugin_id,
            _no_setup,
            requires=inject,
            optional=optional_inject,
            provides=provides,
        )
        self._kernel_context = Context(self.kernel, spec, self._scope)

    def _check(self, name: str) -> None:
        if self._closed:
            raise RuntimeError("Plugin scope is closed")
        declared = name in self._inject or name in self._optional_inject
        if name not in self.granted and not declared:
            raise CapabilityNotGranted(
                f"插件 {self.plugin_id} 未声明 capability '{name}'"
            )

    @property
    def events(self) -> FakeEvents:
        """Returns the granted event fake."""
        self._check("events")
        return self._events

    def expose(self, api: object) -> None:
        """Records a plugin's public export."""
        if self._closed:
            raise RuntimeError("Plugin scope is closed")
        self.exported = api

    def provide[T](self, key: Key[T], impl: T) -> None:
        """Publishes ``impl`` on ``kernel`` under a declared ``provides`` key."""
        self._kernel_context.provide(key, impl)

    def require[T](self, key: Key[T]) -> T:
        """The provider of a declared ``inject`` key; see the class docstring."""
        if key.name in self._inject and self.kernel.get(key) is None:
            if (fake := self._service_fake(key)) is not None:
                return fake
        return self._kernel_context.require(key)

    def get[T](self, key: Key[T]) -> T | None:
        """The provider of a declared ``optional_inject`` key, or None."""
        if key.name in self._optional_inject and self.kernel.get(key) is None:
            if (fake := self._service_fake(key)) is not None:
                return fake
        return self._kernel_context.get(key)

    def _service_fake[T](self, key: Key[T]) -> T | None:
        """The attribute fake standing in for a host-provided service key."""
        attribute = _SERVICE_ATTRIBUTES.get(key.name)
        if attribute is None:
            return None
        try:
            return cast(T, getattr(self, attribute))
        except (AttributeError, CapabilityNotGranted):
            return None

    def on[E](self, event_type: type[E], handler: OnHandler[E]) -> None:
        """Joins ``kernel``'s ordered chain of ``event_type``."""
        self._kernel_context.on(event_type, handler)

    def watch[E](self, event_type: type[E], handler: WatchHandler[E]) -> None:
        """Listens read-only to ``event_type`` on ``kernel``."""
        self._kernel_context.watch(event_type, handler)

    async def emit[E](self, event: E) -> E | Veto:
        """Emits through ``kernel``."""
        return await self._kernel_context.emit(event)

    def effect(self, label: str, dispose: Dispose) -> None:
        """Records custom cleanup in registration order."""
        if self._closed:
            raise RuntimeError("Plugin scope is closed")
        self._effects.append((label, dispose))

    async def aclose(self) -> None:
        """Stops subscriptions, then runs all cleanup in reverse registration order."""
        self._closed = True
        self._events.close()
        errors: list[Exception] = await self._scope.close()
        while self._effects:
            _, dispose = self._effects.pop()
            try:
                result = dispose()
                if inspect.isawaitable(result):
                    await result
            except Exception as error:
                errors.append(error)
        if errors:
            raise ExceptionGroup("Plugin cleanup failed", errors)


# Former capability key name -> the fake attribute tests set for it.
_SERVICE_ATTRIBUTES = {
    value.name: "sessions" if value is services.SESSION_STORE else value.name
    for value in vars(services).values()
    if isinstance(value, Key)
}


def read_manifest_keys(
    package_dir: Path,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """``inject``, ``optional_inject`` and ``provides`` of a package's manifest."""
    # PyYAML is the testing extra; the bare wheel still imports this module.
    import yaml

    manifest = package_dir / "manifest.yaml"
    raw = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"manifest.yaml 格式错误，期望 dict: {manifest}")
    values = cast(dict[str, object], raw)

    def names(field: str) -> tuple[str, ...]:
        value = values.get(field, [])
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in cast(list[object], value)
        ):
            raise ValueError(f"{field} 必须是服务 Key 名称的列表: {manifest}")
        return tuple(cast(list[str], value))

    return names("inject"), names("optional_inject"), names("provides")


async def _no_setup(context: Context) -> None:
    """The fake's spec is never set up by the kernel; setup runs in the test."""
