from story_simulation._schema import SCHEMA as LEGACY_SCHEMA
from story_simulation.internal._schema import SCHEMA


def test_schema_legacy_export_points_to_internal_definition() -> None:
    assert LEGACY_SCHEMA is SCHEMA
    assert "CREATE TABLE IF NOT EXISTS stories" in SCHEMA

