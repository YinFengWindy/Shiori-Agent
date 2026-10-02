"""In-memory role snapshots and opaque namespaces for plugin policy tests."""

from contextlib import nullcontext
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Callable
from shiori_sdk.roles import DraftWriter, RoleProjector


@dataclass
class FakeRole:
    """Only the detached fields needed by plugin tests, with no host services."""

    id: str
    name: str = ""
    system_prompt: str = ""
    description: str = ""
    background: str = ""
    chat_background: str | None = None
    illustrations: list[str] = field(default_factory=list)
    asset_categories: list["FakeCategory"] = field(default_factory=list)
    asset_category_bindings: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Project the fixture's snapshot without runtime configuration."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "background": self.background,
            "illustrations": list(self.illustrations),
        }


@dataclass(frozen=True)
class FakeCategory:
    """One independent role asset category."""

    id: str
    name: str
    allow_role_send: bool = False


class FakeRoleExtensions:
    """Detached opaque data and active draft participants; no manifest storage."""

    def __init__(self):
        self.values: dict[str, dict[str, object]] = {}
        self.participants: dict[str, tuple[DraftWriter, RoleProjector]] = {}

    def read(self, plugin_id: str) -> dict[str, object]:
        """Read an independent copy of one namespace."""
        return deepcopy(self.values.get(plugin_id, {}))

    def update(
        self, plugin_id: str, mutate: Callable[[dict[str, object]], None]
    ) -> None:
        """Apply a mutation to one test namespace."""
        values = self.read(plugin_id)
        mutate(values)
        self.values[plugin_id] = values

    def register(self, plugin_id: str, write: DraftWriter, project: RoleProjector):
        """Record the participant until explicitly disposed."""
        self.participants[plugin_id] = (write, project)

        def dispose() -> None:
            self.participants.pop(plugin_id, None)

        return dispose


class FakeRoles:
    """Explicit fixture roles and asset roots; never opens a host RoleStore."""

    def __init__(self, workspace: Path):
        self.root = workspace / "fixture-assets"
        self.values: dict[str, FakeRole] = {}
        self.extensions = FakeRoleExtensions()

    def create_role(
        self, *, role_id: str, name: str, system_prompt: str, description: str = ""
    ) -> FakeRole:
        """Seed a test snapshot."""
        role = FakeRole(role_id, name, system_prompt, description)
        self.values[role_id] = role
        return role

    def get_role(self, role_id: str) -> FakeRole | None:
        """Read the seeded fixture role."""
        return self.values.get(role_id)

    def list_roles(self) -> list[FakeRole]:
        """List the explicitly seeded roles."""
        return list(self.values.values())

    def asset_path(self, relative_path: str) -> Path:
        """Resolve only the explicit fake asset root."""
        return self.root / relative_path

    def add_illustration(self, role_id: str, source: Path) -> str:
        """Record asset adoption using a fixture-owned copy."""
        target = self.root / role_id / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        relative = target.relative_to(self.root).as_posix()
        self.values[role_id].illustrations.append(relative)
        return relative

    def set_chat_background(self, role_id: str, path: str) -> bool:
        """Record a background choice."""
        self.values[role_id].chat_background = path
        return path in self.values[role_id].illustrations

    def read_scope(self):
        """Tests have a single writer; real lock behavior remains host integration."""
        return nullcontext()
