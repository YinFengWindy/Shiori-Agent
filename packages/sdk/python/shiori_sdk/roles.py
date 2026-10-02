"""Role snapshots, assets and plugin namespaces, without a role-store aggregate."""

from collections.abc import Callable, Sequence
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


type DraftWriter = Callable[[str, dict[str, object], dict[str, object]], None]
type RoleProjector = Callable[[str, dict[str, object]], dict[str, object]]


class RoleExtensions(Protocol):
    """Plugin-owned opaque values participating in the host's atomic role save."""

    def read(self, plugin_id: str) -> dict[str, object]: ...
    def update(
        self, plugin_id: str, mutate: Callable[[dict[str, object]], None]
    ) -> None: ...
    def register(
        self, plugin_id: str, write: DraftWriter, project: RoleProjector
    ) -> Callable[[], None]: ...


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


class SceneObservations(Protocol):
    """Request observations only while the current plugin generation is alive."""

    def request(self, predicate: Callable[[RoleView], bool]) -> None: ...
