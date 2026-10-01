from pathlib import Path

import pytest
from core.memory.markdown.runtime import resolve_markdown_store


def test_resolve_markdown_store_requires_role_id(tmp_path: Path):
    with pytest.raises(ValueError, match="role_id required for markdown memory access"):
        resolve_markdown_store(workspace=tmp_path)
