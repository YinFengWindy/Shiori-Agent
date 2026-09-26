from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _text(value: Any) -> str:
    return str(value or "").strip()


@dataclass
class RoleCharacterDefinition:
    """Stable role identity and behavior consumed by runtime prompts."""

    profile: str = ""
    personality: str = ""
    behavior_rules: str = ""
    response_constraints: str = ""
    nickname: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "profile": self.profile,
            "personality": self.personality,
            "behavior_rules": self.behavior_rules,
            "response_constraints": self.response_constraints,
            "nickname": self.nickname,
        }

    @classmethod
    def from_dict(cls, payload: Any) -> "RoleCharacterDefinition":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            profile=_text(data.get("profile")),
            personality=_text(data.get("personality")),
            behavior_rules=_text(data.get("behavior_rules")),
            response_constraints=_text(data.get("response_constraints")),
            nickname=_text(data.get("nickname")),
        )


@dataclass
class ImportProvenance:
    """Imported card attribution, excluded from runtime prompt rendering."""

    format: str
    card_version: str | None = None
    creator: str = ""
    tags: list[str] = field(default_factory=list)
    source: list[str] = field(default_factory=list)
    created_at: str | int | float | None = None
    updated_at: str | int | float | None = None
    imported_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "card_version": self.card_version,
            "creator": self.creator,
            "tags": list(self.tags),
            "source": list(self.source),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "imported_at": self.imported_at,
        }

    @classmethod
    def from_dict(cls, payload: Any) -> "ImportProvenance | None":
        if not isinstance(payload, dict):
            return None
        value = _text(payload.get("format"))
        if not value:
            return None
        return cls(
            format=value,
            card_version=_text(payload.get("card_version")) or None,
            creator=_text(payload.get("creator")),
            tags=list(payload.get("tags") or []),
            source=list(payload.get("source") or []),
            created_at=payload.get("created_at"),
            updated_at=payload.get("updated_at"),
            imported_at=_text(payload.get("imported_at")),
        )


@dataclass
class RoleProfile:
    """Versioned Shiori runtime role definition."""

    version: int = 1
    character: RoleCharacterDefinition = field(default_factory=RoleCharacterDefinition)
    import_provenance: ImportProvenance | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "version": int(self.version),
            "character": self.character.to_dict(),
        }
        if self.import_provenance is not None:
            payload["import_provenance"] = self.import_provenance.to_dict()
        return payload

    @classmethod
    def from_dict(cls, payload: Any) -> "RoleProfile":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            version=max(1, int(data.get("version") or 1)),
            character=RoleCharacterDefinition.from_dict(data.get("character")),
            import_provenance=ImportProvenance.from_dict(data.get("import_provenance")),
        )

    @classmethod
    def from_legacy(cls, *, system_prompt: str, background: str) -> "RoleProfile":
        return cls(
            character=RoleCharacterDefinition(
                profile=_text(background),
                behavior_rules=_text(system_prompt),
            )
        )
