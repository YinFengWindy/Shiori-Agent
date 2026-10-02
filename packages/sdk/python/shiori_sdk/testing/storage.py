"""Opaque plugin key/value fixture storage."""


class FakeKV:
    """Opaque values retained in one test-owned dictionary."""

    def __init__(self):
        self.values: dict[str, object] = {}

    def get(self, key: str, default: object = None) -> object:
        """Read a seeded value."""
        return self.values.get(key, default)

    def set(self, key: str, value: object) -> None:
        """Record a plugin value."""
        self.values[key] = value
