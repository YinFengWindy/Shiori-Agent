# Natural chat plugin tests

This package uses only `shiori-sdk[testing]` fakes. From a standalone plugin copy,
install the SDK wheel supplied by the matching host build and run:

```sh
uv venv .venv --python 3.12
uv pip install --python .venv --find-links /absolute/path/to/wheelhouse --refresh-package shiori-sdk ".[test]"
uv run --no-project --python .venv python -m pytest -c pyproject.toml tests
```

In the repository, run `uv run pytest plugins/natural_chat/tests`. Verify the
standalone wheel boundary with
`uv run python -m scripts.verify_plugin_tests --plugins natural_chat`.
