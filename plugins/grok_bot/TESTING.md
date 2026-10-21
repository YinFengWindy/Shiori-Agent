# Tests

Repository: `uv run python -m pytest plugins/grok_bot/tests`.

Grok is a bundled plugin. Its backend is discovered from the host plugin root;
the desktop build imports `ui/index.tsx` and stages `client.ps1` with the backend.
It does not require an external ZIP or a precompiled `renderer/ui.mjs` in source.
The host discovery/default tests and desktop builtin-entry/staging tests cover
these distribution boundaries:

```sh
uv run python -m pytest tests/backend/agent/plugin_host/test_discovery.py tests/backend/agent/plugin_host/test_manifest.py
node --test apps/desktop/scripts/builtin-plugin-entries.test.mjs apps/desktop/scripts/runtime-plugin-staging.test.mjs
pnpm --filter shiori-desktop build
```

From a copied plugin and private wheelhouse:

```sh
uv venv .venv --python 3.12
uv pip install --python .venv --find-links /absolute/path/to/wheelhouse --refresh-package shiori-sdk ".[test]"
uv run --no-project --python .venv python -m pytest -c pyproject.toml tests
```

Tests use only SDK fakes and local loopback sockets; Webhook HTTP is mocked.
The client test runs real Windows PowerShell when installed, otherwise skips
that platform-specific case. It never calls a real Grok routine or model.

For desktop acceptance, use an isolated workspace/profile without model
registrations. Confirm the builtin row starts disabled, enable it, and open the
Grok account form for a disposable role. The shown callback client must resolve
inside the current builtin package; the connection file remains in that isolated
workspace's `plugin-data/grok_bot`. Do not reuse a user's real Webhook to verify
the distribution change.

Connection/budget changes (#891) use the focused plugin suite plus:

```sh
pnpm desktop:test --file plugins/grok_bot/ui --file accounts/AccountResponseRulesEditor --file accounts/RoleAccountsPanel --file packages/sdk/src/account/account.test
```

Activation must make no Webhook requests; actual messages work without a handshake
but still require the local token. Budget coverage includes interleaved chains
(A uses 10, B uses 2, B's third message succeeds), chain exhaustion isolation,
deduplication/restart, migration of complete legacy graphs, and closed migration
of previously pruned graphs. Retention evicts only whole settled chains and never
unresolved queued/sending/uncertain work. Desktop acceptance checks routine preview
and exact copy, activation/deactivation, and the remaining full-tools grant; there
are no private/blacklist controls or message status/reset panel for fixed peers.
