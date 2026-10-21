# Tests

Repository: `uv run python -m pytest plugins/grok_bot/tests`.

From a copied plugin and private wheelhouse:

```sh
uv venv .venv --python 3.12
uv pip install --python .venv --find-links /absolute/path/to/wheelhouse --refresh-package shiori-sdk ".[test]"
uv run --no-project --python .venv python -m pytest -c pyproject.toml tests
```

Tests use only SDK fakes and local loopback sockets; Webhook HTTP is mocked.
The client test runs real Windows PowerShell when installed, otherwise skips
that platform-specific case. It never calls a real Grok routine or model.
