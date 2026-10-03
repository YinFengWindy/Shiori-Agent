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

Before launch, acceptance compares the prepared runtime manifest with the plugin's
pin and verifies the local agent-browser executable's SHA256. The evidence records
that actual digest, so an old executable cannot pass under newer version metadata.

Each case writes its own evidence subdirectory: `acceptance.json` records every
attempt, elapsed time, generation, exceptions, cleanup warnings and remaining
owned PIDs; `daemon-NN.log` retains each generation before profile reuse can
overwrite it. Empty native logs are preserved too. Failures remain test failures;
the recorder does not retry operations or change timeouts. Use a different
evidence directory for each repeated run.

The native/CDP stalls investigated in
[#636](https://github.com/YinFengWindy/Shiori-Agent/issues/636) were caused by
agent-browser 0.38.1 leaving Chrome's stderr pipe unread after startup. Once the
pipe filled, synchronous logging could block Chrome operations. Cancellation was
not required to trigger the stall. Upstream
[PR #2003](https://github.com/vercel-labs/agent-browser/pull/2003) adds continuous
draining and is included in the pinned 0.38.2 release.

Both acceptance cases pass with the official 0.38.2 executable and the unchanged
Chrome for Testing 153.0.8010.52. They verify three browser generations, profile
reuse, cancellation of in-flight and queued work, and final tab closure without
diagnostic builds or manual pipe draining. The daemon fingerprint and cached core
tool schemas remain compatible; timeout, retry and browser launch flags are unchanged.
