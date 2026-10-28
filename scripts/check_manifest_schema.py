"""Validate every plugins/*/manifest.yaml against packages/sdk/manifest.schema.json.

The schema describes the current manifest format.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "packages/sdk/manifest.schema.json"


def violations(root: Path, schema: dict[str, object]) -> tuple[list[str], int]:
    """Schema errors of the plugin manifests below ``root/plugins`` and their count."""
    validator = Draft202012Validator(schema)
    manifests = sorted((root / "plugins").glob("*/manifest.yaml"))
    errors: list[str] = []
    for manifest in manifests:
        name = manifest.relative_to(root).as_posix()
        raw = yaml.safe_load(manifest.read_text(encoding="utf-8"))
        for error in validator.iter_errors(raw):
            location = ".".join(str(part) for part in error.absolute_path) or "<root>"
            errors.append(f"{name}: {location}: {error.message}")
    return errors, len(manifests)


def main() -> None:
    """Fail on a malformed schema or a nonconforming manifest."""
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    errors, count = violations(ROOT, schema)
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"{count} plugin manifests match packages/sdk/manifest.schema.json")


if __name__ == "__main__":
    main()
