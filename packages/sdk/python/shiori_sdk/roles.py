"""Role snapshots, assets and plugin namespaces, without a role-store aggregate."""

from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Protocol


class RoleCategory(Protocol):
    """Read-only sendability metadata for one role asset category."""

    @property
    def id(self) -> str: ...
    @property
    def name(self) -> str: ...
    @property
    def allow_role_send(self) -> bool: ...


class RoleView(Protocol):
    """A detached role snapshot; no runtime, accounts, storage or write lock."""

    @property
    def id(self) -> str: ...
    @property
    def illustrations(self) -> list[str]: ...
    @property
    def asset_categories(self) -> Sequence[RoleCategory]: ...
    @property
    def asset_category_bindings(self) -> dict[str, str]: ...
    def to_dict(self) -> dict[str, object]: ...


# A participant mutates only its detached namespace; persistence stays with the host.
type DraftWriter = Callable[[str, dict[str, object], dict[str, object]], None]
# A read-only result permits precise plugin value types such as dict[str, bool].
type RoleProjector = Callable[[str, dict[str, object]], Mapping[str, object]]


class RoleExtensions(Protocol):
    """Plugin-owned opaque values participating in the host's atomic role save."""

    def read(self, plugin_id: str) -> dict[str, object]: ...
    def update(
        self, plugin_id: str, mutate: Callable[[dict[str, object]], None]
    ) -> None: ...
    def register(
        self, plugin_id: str, write: DraftWriter, project: RoleProjector
    ) -> Callable[[], None]: ...


class PluginSettings(Protocol):
    """Opaque read/write of one role namespace.

    ``proactive`` is the namespace that exists today. The 4.0 host still parses
    that namespace with the core proactive config until proactive leaves the
    core. 4.x cannot add methods here later (D19, D22).
    """

    def read(self) -> Mapping[str, object]:
        """The stored object for this namespace."""
        ...

    def write(self, value: Mapping[str, object]) -> None:
        """Replace the stored object for this namespace."""
        ...


class Roles(Protocol):
    """Only operations consumed by role-based plugins; canonical storage stays host-owned."""

    def get_role(self, role_id: str) -> RoleView | None: ...
    def list_roles(self) -> Sequence[RoleView]: ...
    def asset_path(self, relative_path: str) -> Path: ...
    def add_illustration(self, role_id: str, source: Path) -> str: ...
    def set_chat_background(self, role_id: str, path: str) -> bool: ...
    def read_scope(self) -> AbstractContextManager[object]: ...
    @property
    def extensions(self) -> RoleExtensions: ...
    def plugin_settings(self, role_id: str, namespace: str) -> PluginSettings:
        """Read and write one role's opaque namespace (D19).

        ``roleSettings`` on the renderer is a separate slot and already exists.
        Unknown ``namespace`` fails. Only ``proactive`` is stored today.
        """
        ...
