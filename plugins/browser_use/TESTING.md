# Independent plugin tests

This package uses `shiori-sdk[testing]` and its declared dependencies. It does not
install the host, host test support, or another plugin's test extra.

From a copy outside the repository with a private wheelhouse available:

```sh
uv venv .venv --python 3.12
uv pip install --python .venv --find-links /absolute/path/to/wheelhouse --refresh-package shiori-sdk ".[test]"
uv run --no-project --python .venv python -m pytest -c pyproject.toml tests
```

Tests supply explicit SDK capabilities for role/model/storage/network/process
boundaries. Real kernel integration, persistence, runtime leases and Windows
owned-process cleanup run in the host's `tests/backend/` tree.

## Fixed Windows runtime acceptance

From a host checkout with its own `.venv`, prepare the pinned assets with
`pnpm prepare:browser-use`, then run the opt-in host test:

```powershell
$env:SHIORI_BROWSER_USE_RUNTIME = (Resolve-Path native/browser-use).Path
$env:SHIORI_BROWSER_USE_EVIDENCE = (Join-Path (Get-Location) '.scratch/browser-acceptance')
.venv\Scripts\pytest.exe tests/backend/agent/plugin_host/test_processes_browser_use.py -q
```

The `complete` case covers local-page interaction, screenshots, persistence,
cancellation and recovery. The `recovery` case keeps the same native MCP,
headless configuration, profile reuse, in-flight cancellation, queued call and
third-generation open/tab-close sequence, omitting the preceding form/screenshot
and multi-tab interaction. Select either with `-k complete` or `-k recovery`.
Each case uses a fresh isolated profile and a local HTTP server.

Each case writes its own evidence subdirectory: `acceptance.json` records every
attempt, elapsed time, generation, exceptions, cleanup warnings and remaining
owned PIDs; `daemon-NN.log` retains each generation before profile reuse can
overwrite it. Empty native logs are preserved too. Failures remain test failures;
the recorder does not retry operations or change timeouts. Use a different
evidence directory for each repeated run.

The pinned runtime's intermittent native/CDP failures remain under investigation
in [#636](https://github.com/YinFengWindy/Shiori-Agent/issues/636). They have also
occurred in the first generation, so cancellation is not a necessary trigger.
