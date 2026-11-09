"""Presentation selection and visibility, independent of model formats."""

from dataclasses import dataclass
from typing import Any, TypedDict
from shiori_sdk.services import ServiceReference


class SelectedModel(TypedDict):
    """Persisted model identity owned by a presentation provider."""

    provider: ServiceReference
    model_id: str


def read_provider(value: object) -> ServiceReference:
    """Reject incomplete service identities at the RPC boundary."""
    if not isinstance(value, dict):
        raise ValueError("缺少形象提供者")
    plugin_id, service_id = value.get("plugin_id"), value.get("service_id")
    if (
        not isinstance(plugin_id, str)
        or not plugin_id.strip()
        or not isinstance(service_id, str)
        or not service_id.strip()
    ):
        raise ValueError("形象提供者身份无效")
    return {"plugin_id": plugin_id, "service_id": service_id}


def read_selection(value: object) -> SelectedModel | None:
    """Read a reference without requiring its provider to be installed."""
    if value is None:
        return None
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("model_id"), str)
        or not value["model_id"].strip()
    ):
        raise ValueError("形象选择无效")
    return {
        "provider": read_provider(value.get("provider")),
        "model_id": value["model_id"],
    }


@dataclass
class RolePetState:
    """Desktop-owned intent; unavailable providers never erase this state."""

    id: str
    selected_model: SelectedModel | None = None
    desktop_pet_enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize desktop-owned fields only."""
        return {
            "selected_model": self.selected_model,
            "desktop_pet_enabled": self.desktop_pet_enabled,
        }

    @classmethod
    def from_dict(cls, role_id: str, payload: object) -> "RolePetState":
        """Read legacy selection until its provider safely adopts the assets."""
        if not isinstance(payload, dict):
            raise ValueError("桌宠角色状态必须是对象")
        selected: SelectedModel | None
        if "selected_model" in payload:
            selected = read_selection(payload["selected_model"])
        else:
            old_id = payload.get("selected_pet_package_id")
            installed = {
                item.get("id")
                for item in payload.get("pet_packages", [])
                if isinstance(item, dict)
            }
            selected = (
                {
                    "provider": {
                        "plugin_id": "pet_codex_sprite",
                        "service_id": "models",
                    },
                    "model_id": old_id,
                }
                if isinstance(old_id, str) and old_id in installed
                else None
            )
        return cls(
            role_id, selected, bool(selected and payload.get("desktop_pet_enabled"))
        )
