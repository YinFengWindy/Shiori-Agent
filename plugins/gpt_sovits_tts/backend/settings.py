"""Validated connection and role sound documents owned by this plugin."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from shiori_sdk.files.json import atomic_save_json, load_json
from shiori_sdk.local_http import loopback_http_url
from shiori_sdk.storage import plugin_data_dir

type Language = Literal[
    "auto",
    "auto_yue",
    "zh",
    "en",
    "ja",
    "ko",
    "yue",
    "all_zh",
    "all_ja",
    "all_ko",
    "all_yue",
]


class Settings(BaseModel):
    """Explicit v2ProPlus weights; relative paths resolve in the external server."""

    model_config = ConfigDict(extra="forbid", strict=True)
    connection_mode: Literal["external", "managed"] = "external"
    url: str = "http://127.0.0.1:9880"
    version: Literal["v2ProPlus"] = "v2ProPlus"
    gpt_weights: str = Field(
        default="GPT_SoVITS/pretrained_models/s1v3.ckpt", min_length=1
    )
    sovits_weights: str = Field(
        default="GPT_SoVITS/pretrained_models/v2Pro/s2Gv2ProPlus.pth", min_length=1
    )
    validate_url = field_validator("url")(loopback_http_url)


class Reference(BaseModel):
    """Immutable owned audio identity and the matching prompt transcription."""

    model_config = ConfigDict(extra="forbid", strict=True)
    asset: str = Field(pattern=r"^[a-f0-9]{32}\.wav$")
    prompt_text: str = Field(default="", max_length=10000)
    prompt_lang: Language = "zh"


class RoleVoice(BaseModel):
    """One default reference and optional explicit mood-to-reference overrides."""

    model_config = ConfigDict(extra="forbid", strict=True)
    text_lang: Language = "auto"
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    default: Reference | None = None
    moods: dict[str, Reference] = Field(default_factory=dict, max_length=64)


class Document(BaseModel):
    """Only plugin-owned data is persisted; role IDs are foreign identities."""

    model_config = ConfigDict(extra="forbid", strict=True)
    settings: Settings = Field(default_factory=Settings)
    roles: dict[str, RoleVoice] = Field(default_factory=dict)


class VoiceStore:
    """Keep settings and role sound mappings in one atomically replaced document."""

    def __init__(self, workspace: Path):
        self.root = plugin_data_dir(workspace, "gpt_sovits_tts")
        self.path = self.root / "voices.json"

    def read(self) -> Document:
        """Read a detached validated document, never silently reset corruption."""
        return Document.model_validate(load_json(self.path, {}))

    def write(self, document: Document) -> None:
        """Commit an already validated snapshot synchronously."""
        atomic_save_json(self.path, document.model_dump(mode="json"))

    def save_settings(self, values: dict[str, object]) -> Settings:
        """Replace only connection settings, preserving all role references."""
        document = self.read()
        document.settings = Settings.model_validate(values)
        self.write(document)
        return document.settings

    def save_role(self, role_id: str, values: object) -> RoleVoice:
        """Replace one private role mapping."""
        document = self.read()
        voice = RoleVoice.model_validate(values)
        document.roles[role_id] = voice
        self.write(document)
        return voice
