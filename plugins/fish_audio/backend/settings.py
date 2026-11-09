"""Private connection settings and per-role voices, saved atomically."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from shiori_sdk.files.json import atomic_save_json, load_json
from shiori_sdk.storage import plugin_data_dir

type TtsModel = Literal["s2.1-pro-free", "s2.1-pro", "s2-pro"]
type TextLanguage = Literal[
    "auto",
    "zh-CN",
    "zh-TW",
    "en",
    "ja",
    "ko",
    "es-ES",
    "es-MX",
    "fr",
    "de",
    "it",
    "pt-BR",
    "ru",
    "ar",
    "tr",
    "fil",
]


class Settings(BaseModel):
    """Credentials never leave the plugin through a settings read."""

    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    api_key: str = Field(default="", max_length=4096, repr=False)
    tts_model: TtsModel = "s2.1-pro-free"


class SettingsUpdate(BaseModel):
    """An omitted/blank key preserves the secret; clearing is explicit."""

    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    api_key: str = Field(default="", max_length=4096, repr=False)
    tts_model: TtsModel
    clear_api_key: bool = False


class RoleVoice(BaseModel):
    """One role's Fish voice, speed and text-normalization language."""

    model_config = ConfigDict(extra="forbid", strict=True)
    reference_id: str = Field(default="", max_length=256)
    speed: float = Field(default=1.0, ge=0.5, le=2.0, allow_inf_nan=False)
    language: TextLanguage = "auto"

    @field_validator("reference_id")
    @classmethod
    def trim_reference(cls, value: str) -> str:
        """Store a voice ID without surrounding clipboard whitespace."""
        return value.strip()


class Document(BaseModel):
    """Global credentials and isolated role mappings owned by Fish."""

    model_config = ConfigDict(extra="forbid", strict=True)
    settings: Settings = Field(default_factory=Settings)
    roles: dict[str, RoleVoice] = Field(default_factory=dict)


class VoiceStore:
    """Read detached snapshots and replace the private document atomically."""

    def __init__(self, workspace: Path):
        self.path = plugin_data_dir(workspace, "fish_audio") / "voices.json"

    def read(self) -> Document:
        """Reject corrupt data instead of replacing it with defaults."""
        return Document.model_validate(load_json(self.path, {}))

    def write(self, document: Document) -> None:
        """Persist a validated document."""
        atomic_save_json(self.path, document.model_dump(mode="json"))

    def public_settings(self) -> dict[str, object]:
        """Return configuration without disclosing the credential."""
        settings = self.read().settings
        return {"tts_model": settings.tts_model, "has_api_key": bool(settings.api_key)}

    def save_settings(self, values: dict[str, object]) -> dict[str, object]:
        """Change global settings without overwriting any role voice."""
        update = SettingsUpdate.model_validate(values)
        document = self.read()
        key = update.api_key.strip()
        if update.clear_api_key and key:
            raise ValueError("不能同时设置和清除 API Key")
        if update.clear_api_key:
            document.settings.api_key = ""
        elif key:
            if any(ord(char) < 32 or ord(char) > 126 for char in key):
                raise ValueError("API Key 格式无效")
            document.settings.api_key = key
        document.settings.tts_model = update.tts_model
        self.write(document)
        return self.public_settings()

    def save_role(self, role_id: str, voice: RoleVoice) -> RoleVoice:
        """Replace only the selected role's private voice."""
        document = self.read()
        document.roles[role_id] = voice
        self.write(document)
        return voice

    def reconcile(self, role_ids: set[str]) -> None:
        """Discard mappings for deleted roles, including deletions while disabled."""
        document = self.read()
        retained = {
            key: value for key, value in document.roles.items() if key in role_ids
        }
        if len(retained) != len(document.roles):
            document.roles = retained
            self.write(document)
