"""Host-owned package sources that ship as independently managed workspace plugins."""

from pathlib import Path

from bootstrap.paths import plugin_roots

_INSTALLABLE_PLUGINS = ("tencent_asr", "minimax_tts")


def bundled_plugin_sources() -> dict[str, Path]:
    """Find optional shipped sources; user workspace directories are never sources."""
    sources: dict[str, Path] = {}
    for root in plugin_roots():
        for plugin_id in _INSTALLABLE_PLUGINS:
            directory = (root / plugin_id).absolute()
            if not directory.is_dir():
                continue
            if directory.is_symlink() or directory.resolve() != directory:
                raise ValueError(f"随包插件源不能包含目录链接: {directory}")
            previous = sources.get(plugin_id)
            if previous is not None and previous != directory:
                raise ValueError(f"随包插件源重复: {plugin_id}")
            sources[plugin_id] = directory
    return sources


def is_bundled_plugin_source(directory: Path) -> bool:
    """Exclude only exact distribution assets, never an arbitrary matching plugin ID."""
    return directory.absolute() in bundled_plugin_sources().values()
