"""Static plugin candidates discovered by the host."""

from dataclasses import dataclass, field
from pathlib import Path

from shiori_sdk.kernel import PluginDiagnostic
from agent.plugin_host.manifest import ManifestError, PluginManifest


@dataclass
class PluginRecord:
    """discover() 产出的静态描述：目录、入口与 manifest。"""

    name: str
    plugin_dir: Path
    entry_file: Path
    import_path: str
    manifest: PluginManifest
    source: str = "builtin"
    admission: PluginDiagnostic | None = None
    # Captured before execution and retained across settings generations.
    fingerprint: str | None = None
    trust_directory: str = ""
    content_hashes: dict[str, str] = field(default_factory=dict)

    @property
    def candidate_id(self) -> str:
        """Identify one directory candidate without collapsing duplicate manifest IDs."""
        return str(self.plugin_dir.absolute())

    @property
    def is_conflicting(self) -> bool:
        """Whether discovery excluded this candidate from dependency lookup."""
        return self.admission is not None and self.admission.state == "CONFLICT"


def records_by_id(records: list[PluginRecord]) -> dict[str, PluginRecord]:
    """Select unambiguous candidates that may participate in dependencies."""
    return {
        record.manifest.id: record for record in records if not record.is_conflicting
    }


def find_record(records: list[PluginRecord], name: str) -> PluginRecord | None:
    """Find an exact directory candidate or an unambiguous name or manifest id."""
    exact = [record for record in records if record.candidate_id == name]
    matches = exact or [
        record
        for record in records
        if record.name == name or record.manifest.id == name
    ]
    if len(matches) > 1:
        raise ManifestError(f"插件名称不唯一，请使用候选目录标识: {name}")
    return matches[0] if matches else None
