"""Default-engine status and private-field presentation rules."""

SEMANTIC_STATUS_FILTERS: tuple[str, ...] = ("active", "superseded", "all")
"""Status filter values an engine declares when it can filter by item status."""


def readable_item(item: dict[str, object]) -> dict[str, object]:
    """Drop vector and hash fields from the read-only Dashboard response."""
    visible = {
        key: value
        for key, value in item.items()
        if key not in {"embedding", "embedding_dim", "content_hash", "has_embedding"}
    }
    extra = visible.get("extra_json")
    if isinstance(extra, dict):
        visible["extra_json"] = {
            key: value
            for key, value in extra.items()
            if key not in {"embedding", "embedding_dim", "content_hash"}
        }
    return visible
