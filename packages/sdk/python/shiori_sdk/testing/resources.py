"""Explicit resource paths for independent plugin tests."""

from pathlib import Path


class FakeResources:
    """Use explicitly supplied test paths for packaged resources."""

    def __init__(self, root: Path):
        self.root = root

    def common_emojis(self, workspace: Path) -> tuple[Path, ...]:
        """Resolve fixture emoji files without knowing any repository layout."""
        return (workspace / "common_emojis.json", self.root / "common_emojis.json")
