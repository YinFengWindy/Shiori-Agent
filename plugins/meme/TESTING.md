# Independent plugin tests

This package uses `shiori-sdk[testing]` and its declared dependencies. It does not
install the host, host test support, or another plugin's test extra.

From a copy outside the repository with a private wheelhouse available:

```sh
uv venv .venv --python 3.12
uv pip install --python .venv --find-links /absolute/path/to/wheelhouse --refresh-package shiori-sdk --refresh-package shiori-plugin-citation ".[test]"
uv run --no-project --python .venv python -m pytest -c pyproject.toml tests
```

Tests supply explicit SDK capabilities for role/model/storage/network/process
boundaries. Real kernel integration, persistence, runtime leases and Windows
owned-process cleanup run in the host's `tests/backend/` tree.
