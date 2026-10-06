"""Owned immutable references and deferred reclamation around actual inference."""

from collections import Counter
from contextlib import contextmanager
from pathlib import Path

from shiori_sdk.files.assets import copy_owned_asset
from shiori_sdk.files.audio import pcm_wav_duration
from shiori_sdk.files.staging import staged_import_file

from .settings import RoleVoice, VoiceStore


class References:
    """Pin files while an external server may still read their absolute paths."""

    def __init__(self, store: VoiceStore):
        self.store = store
        self.directory = store.root / "references"
        self.pins: Counter[str] = Counter()
        self.imported: set[str] = set()
        self.retired: set[str] = set()

    def import_file(self, workspace: Path, source: str) -> dict[str, object]:
        """Validate a 3–10 second signal before adopting a native-picker WAV."""
        path = staged_import_file(
            workspace,
            "gpt_sovits_tts-audio",
            source,
            suffix=".wav",
            max_bytes=32 * 1024 * 1024,
        )
        try:
            duration = pcm_wav_duration(path.read_bytes(), require_signal=True)
            if not 3 <= duration <= 10:
                raise ValueError("参考音频必须为 3–10 秒 PCM WAV")
            target = copy_owned_asset(path, self.directory)
            self.imported.add(target.name)
            return {"asset": target.name, "duration": duration}
        finally:
            path.unlink(missing_ok=True)

    def path(self, asset: str) -> Path:
        """Resolve only an immutable owned file; saved models validate its name."""
        path = self.directory / asset
        if (
            path.name != asset
            or path.resolve().parent != self.directory.resolve()
            or not path.is_file()
        ):
            raise ValueError("参考音频不存在，请重新导入")
        return path.resolve()

    def validate(self, voice: RoleVoice) -> None:
        """Reject stale asset identities before a private role save."""
        for reference in [voice.default, *voice.moods.values()]:
            if reference is not None:
                self.path(reference.asset)

    @contextmanager
    def pin(self, asset: str):
        """Retain the reference through weight switching and full HTTP completion."""
        path = self.path(asset)
        self.pins[asset] += 1
        try:
            yield path
        finally:
            self.pins[asset] -= 1
            self.retired.add(asset)
            self.collect()

    def retire(self, voice: RoleVoice) -> None:
        """Track previously committed files without sweeping another editor's imports."""
        self.retired.update(
            ref.asset for ref in [voice.default, *voice.moods.values()] if ref
        )

    def collect(self, *, sweep: bool = False) -> None:
        """Reclaim unused files only when no uncertain server operation can read them."""
        if (self.store.root / "inference.json").exists():
            return
        keep = set(self.imported) | {
            asset for asset, count in self.pins.items() if count
        }
        for voice in self.store.read().roles.values():
            keep.update(
                ref.asset for ref in [voice.default, *voice.moods.values()] if ref
            )
        if self.directory.exists():
            candidates = (
                self.directory.glob("*.wav")
                if sweep
                else (self.directory / name for name in tuple(self.retired))
            )
            for path in candidates:
                if path.name not in keep:
                    path.unlink(missing_ok=True)
                    self.retired.discard(path.name)

    def reconcile(self, existing_roles: set[str], *, sweep: bool = False) -> None:
        """Remove deleted roles on restart; keep uncertain in-flight assets untouched."""
        document = self.store.read()
        for role_id, voice in document.roles.items():
            if role_id not in existing_roles:
                self.retire(voice)
        remaining = {
            key: value for key, value in document.roles.items() if key in existing_roles
        }
        if len(remaining) != len(document.roles):
            document.roles = remaining
            self.store.write(document)
        self.collect(sweep=sweep)
