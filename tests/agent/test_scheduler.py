from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.scheduler import JobStore


def test_job_store_raises_for_invalid_json(tmp_path: Path):
    path = tmp_path / "jobs.json"
    path.write_text("[broken", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        JobStore(path).load()


def test_job_store_raises_for_invalid_job_payload(tmp_path: Path):
    path = tmp_path / "jobs.json"
    path.write_text('[{"id": "incomplete"}]', encoding="utf-8")

    with pytest.raises((KeyError, TypeError)):
        JobStore(path).load()
