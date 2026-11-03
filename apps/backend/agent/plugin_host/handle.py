"""Static plugin candidates discovered by the host."""

from dataclasses import dataclass, field
from pathlib import Path

from shiori_sdk.kernel import PluginDiagnostic
from agent.plugin_host.manifest import PluginManifest


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
