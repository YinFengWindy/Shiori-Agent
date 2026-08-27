from __future__ import annotations

import json
import threading
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ManagedVoiceAsset:
    """A provider voice that Shiori is authorized to delete."""

    provider: str
    voice_id: str
    ownership: str = "shiori_managed"

    def to_dict(self) -> dict[str, str]:
        return {
            "provider": self.provider,
            "voice_id": self.voice_id,
            "ownership": self.ownership,
        }


def managed_voice_asset(runtime_config: object) -> ManagedVoiceAsset | None:
    """Extracts one managed TTS asset from a role runtime configuration."""

    config = runtime_config if isinstance(runtime_config, Mapping) else {}
    raw_tts = config.get("tts")
    tts = raw_tts if isinstance(raw_tts, Mapping) else {}
    provider = str(tts.get("provider") or "").strip()
    voice_id = str(tts.get("voice_id") or "").strip()
    ownership = str(tts.get("ownership") or "").strip()
    if provider and voice_id and ownership == "shiori_managed":
        return ManagedVoiceAsset(provider=provider, voice_id=voice_id)
    return None


class VoiceAssetLifecycle:
    """Persists managed-clone cleanup until the provider accepts deletion."""

    def __init__(
        self,
        workspace: Path,
        delete_managed_voice: Callable[..., None],
    ) -> None:
        self._path = workspace / "voice_asset_cleanup.json"
        self._delete_managed_voice = delete_managed_voice
        self._lock = threading.RLock()
        self._tracked, self._retired = self._load()

    def track_clone(self, result: Mapping[str, Any]) -> None:
        """Durably records a clone until a role save claims or discards it."""

        asset = ManagedVoiceAsset(
            provider=str(result.get("provider") or "").strip(),
            voice_id=str(result.get("voice_id") or "").strip(),
            ownership=str(result.get("ownership") or "").strip(),
        )
        if (
            not asset.provider
            or not asset.voice_id
            or asset.ownership != "shiori_managed"
        ):
            raise ValueError("复刻结果缺少受管音色标识")
        self._add_tracked(asset)

    def reconcile_role_update(
        self, previous_runtime: object, current_runtime: object
    ) -> None:
        """Claims a saved clone and retires a replaced managed asset."""

        previous = managed_voice_asset(previous_runtime)
        current = managed_voice_asset(current_runtime)
        if current is not None:
            self._remove(current)
        if previous is not None and previous != current:
            self._retire(previous)

    def retire_deleted_role(self, runtime_config: object) -> None:
        """Queues the deleted role's managed clone for durable cleanup."""

        asset = managed_voice_asset(runtime_config)
        if asset is not None:
            self._retire(asset)

    def abandon_clone(self, *, provider: str, voice_id: str, ownership: str) -> bool:
        """Deletes a still-unclaimed clone and retains it when deletion fails."""

        asset = ManagedVoiceAsset(
            provider=provider.strip(),
            voice_id=voice_id.strip(),
            ownership=ownership.strip(),
        )
        if not self._contains(asset):
            return False
        self._retire(asset)
        return True

    def recover_orphans(self, active_runtime_configs: Iterable[object]) -> None:
        """Drops active references then retries clones left by a prior crashed editor."""

        for runtime_config in active_runtime_configs:
            asset = managed_voice_asset(runtime_config)
            if asset is not None:
                self._remove(asset)
        with self._lock:
            if self._tracked:
                for asset in self._tracked:
                    if asset not in self._retired:
                        self._retired.append(asset)
                self._tracked = []
                self._save()
        self.retry_pending()

    def retry_pending(self) -> None:
        """Attempts every durable cleanup without losing failures."""

        for asset in self.pending_assets:
            try:
                self._delete_managed_voice(
                    provider=asset.provider,
                    voice_id=asset.voice_id,
                    ownership=asset.ownership,
                )
            except Exception:
                continue
            self._remove(asset)

    @property
    def pending_assets(self) -> tuple[ManagedVoiceAsset, ...]:
        with self._lock:
            return tuple(self._retired)

    def _retire(self, asset: ManagedVoiceAsset) -> None:
        with self._lock:
            changed = False
            if asset in self._tracked:
                self._tracked = [item for item in self._tracked if item != asset]
                changed = True
            if asset not in self._retired:
                self._retired.append(asset)
                changed = True
            if changed:
                self._save()
        self.retry_pending()

    def _contains(self, asset: ManagedVoiceAsset) -> bool:
        with self._lock:
            return asset in self._tracked or asset in self._retired

    def _add_tracked(self, asset: ManagedVoiceAsset) -> None:
        with self._lock:
            if asset in self._tracked or asset in self._retired:
                return
            self._tracked.append(asset)
            self._save()

    def _remove(self, asset: ManagedVoiceAsset) -> None:
        with self._lock:
            next_tracked = [item for item in self._tracked if item != asset]
            next_retired = [item for item in self._retired if item != asset]
            if len(next_tracked) == len(self._tracked) and len(next_retired) == len(
                self._retired
            ):
                return
            self._tracked = next_tracked
            self._retired = next_retired
            self._save()

    def _load(self) -> tuple[list[ManagedVoiceAsset], list[ManagedVoiceAsset]]:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return [], []
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("语音音色清理状态无法读取") from exc
        if isinstance(raw, list):
            return [], self._parse_assets(raw)
        if not isinstance(raw, Mapping):
            raise RuntimeError("语音音色清理状态格式无效")
        tracked = raw.get("tracked", [])
        retired = raw.get("retired", [])
        if not isinstance(tracked, list) or not isinstance(retired, list):
            raise RuntimeError("语音音色清理状态格式无效")
        return self._parse_assets(tracked), self._parse_assets(retired)

    @staticmethod
    def _parse_assets(raw: list[object]) -> list[ManagedVoiceAsset]:
        assets: list[ManagedVoiceAsset] = []
        for value in raw:
            if not isinstance(value, Mapping):
                continue
            asset = ManagedVoiceAsset(
                provider=str(value.get("provider") or "").strip(),
                voice_id=str(value.get("voice_id") or "").strip(),
                ownership=str(value.get("ownership") or "").strip(),
            )
            if (
                asset.provider
                and asset.voice_id
                and asset.ownership == "shiori_managed"
                and asset not in assets
            ):
                assets.append(asset)
        return assets

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "tracked": [asset.to_dict() for asset in self._tracked],
                    "retired": [asset.to_dict() for asset in self._retired],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        temporary.replace(self._path)
