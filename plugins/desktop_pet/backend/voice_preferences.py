"""Desktop-pet-owned speech preferences, separate from host and role documents."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from shiori_sdk.files.json import atomic_save_json, load_json
from shiori_sdk.storage import plugin_data_dir


class SelectedService(BaseModel):
    """Exact dynamic service identity, never an implicit provider fallback."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    plugin_id: str = Field(min_length=1, max_length=128)
    service_id: str = Field(min_length=1, max_length=128)


class VoicePreferences(BaseModel):
    """Preferences interpreted by the pet's input and reply controllers."""

    model_config = ConfigDict(extra="forbid", strict=True)
    enabled: bool = False
    hotkey: str = "Ctrl+Space"
    microphone_device_id: str = ""
    asr: SelectedService | None = None
    tts: SelectedService | None = None

    @property
    def speech_on(self) -> bool:
        """Whether the pet speaks replies (mirrors ``speechOn`` in the background)."""
        return self.enabled and self.tts is not None


class VoicePreferencesStore:
    """Read and atomically write only this plugin's private preference file."""

    def __init__(self, workspace: Path) -> None:
        self.path = plugin_data_dir(workspace, "desktop_pet") / "voice-preferences.json"

    def read(self) -> VoicePreferences:
        """Missing preferences start disabled; corrupt saved data remains an error."""
        return VoicePreferences.model_validate(load_json(self.path, {}))

    def write(self, values: dict[str, object]) -> VoicePreferences:
        """Validate the full plugin-owned document before replacing persisted values."""
        preferences = VoicePreferences.model_validate(values)
        atomic_save_json(self.path, preferences.model_dump(mode="json"))
        return preferences
