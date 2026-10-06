"""SenseVoice connection settings persisted exclusively in plugin data."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator
from shiori_sdk.files.json import atomic_save_json, load_json
from shiori_sdk.local_http import loopback_http_url
from shiori_sdk.storage import plugin_data_dir


class Settings(BaseModel):
    """The supported deployment is the official FunASR server on CPU."""

    model_config = ConfigDict(extra="forbid", strict=True)
    connection_mode: Literal["external", "managed"] = "external"
    url: str = "http://127.0.0.1:8000"
    device: Literal["cpu"] = "cpu"
    model: Literal["sensevoice"] = "sensevoice"
    validate_url = field_validator("url")(loopback_http_url)


class SettingsStore:
    """Atomically load/save validated settings, retaining corrupt files as errors."""

    def __init__(self, workspace: Path):
        self.root = plugin_data_dir(workspace, "sensevoice_asr")
        self.path = self.root / "settings.json"

    def read(self) -> Settings:
        """Read a detached settings snapshot."""
        return Settings.model_validate(load_json(self.path, {}))

    def write(self, values: dict[str, object]) -> Settings:
        """Validate before replacing the private settings document."""
        settings = Settings.model_validate(values)
        atomic_save_json(self.path, settings.model_dump())
        return settings
