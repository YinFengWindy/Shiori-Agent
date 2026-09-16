# External Plugin Runtime Contract v1

This contract is the external package boundary for #210 / #261. A package is
validated before its backend is imported. It is **not a sandbox or a trust grant**:
trusted plugin code ultimately runs with the host's privileges.

`package_contract: 1` opts into the package contract. `api: 2` remains the backend
setup protocol. `version` identifies plugin releases; `runtime_api` independently
constrains the host API. Bundled source plugins without `package_contract` retain
the existing v2 build/loading path. An external installer or discovery provider
must call this validator even when the discriminator is absent; omission is not
a way to accept a legacy external package. Source classification/manual trust
(#211/#216), external renderer loading (#213), and cross-host activation rollback
(#262) are separate delivery slices.

## Package layout and schema

A zip contains `manifest.yaml` at its root, without an enclosing directory. The
same root can be placed in a manual package directory. Example:

```text
manifest.yaml
backend/plugin.py
renderer/ui.mjs
renderer/background.mjs
renderer/surface.mjs
style.css
assets/label.txt
```

UTF-8 YAML is required. The executable schema is `validate_package()` in
`apps/backend/agent/plugin_host/package_contract.py`, with shared strict field
readers and renderer validation in the adjacent owning modules. Unknown top-level
and renderer declaration keys are rejected. This table defines the v1 fields:

| Field | Required | Value |
| --- | --- | --- |
| `package_contract` | yes | integer `1` |
| `api` | yes | integer `2` |
| `id` | yes | `[a-z][a-z0-9_-]{0,63}` |
| `version` | yes | full SemVer 2.0 string, including optional prerelease/build |
| `runtime_api` | yes | compatibility range; host currently advertises `2.1.0` |
| `entry` | yes | explicit package-relative `.py` backend entry |
| `capabilities` | yes | existing v2 capability-name list, including `[]` |
| `renderer` | no | object with optional `ui`, `background`, `surface` keys |
| `renderer.<kind>.entry` | per declared kind | package-relative precompiled `.mjs` |
| `renderer.<kind>.css` | per declared kind | list of `.css` files; `[]` explicitly means no styles |
| `assets` | no | list of required package-relative regular files; default `[]` |
| `host_dependencies.python` | no | required host Python distribution names; default `[]` |
| `peer_dependencies` | for any renderer | `react` and `react-dom` compatibility ranges |
| `dependencies`, `optional_dependencies` | no | existing strong/optional plugin ID lists |
| `supports_hot_unload` | no | existing boolean, default `true` |
| `desc`, `author`, `config_model` | no | existing v2 descriptive/configuration metadata |

There is one backend entry in v1. Each renderer kind may declare one entry. Every
declaration is required; there is no `optional` entry flag. A missing stylesheet,
background module or surface entry blocks the whole package before backend import.
A backend entry must be parseable Python with a top-level `async def setup` that
accepts one positional context and has no additional required arguments. The
existing injected context/capability protocol is unchanged. The external fixture
uses that context without importing host internals; public backend import
portability is completed by #212.

Ranges use whitespace-separated comparators with AND semantics: `=`, `>`, `>=`,
`<`, `<=`; a bare SemVer means equality. Example: `>=2.0.0 <3.0.0`. Caret, tilde,
wildcard, comma, OR and hyphen ranges are deliberately unsupported and rejected.
Build metadata does not affect precedence. Prerelease hosts require a comparator
mentioning a prerelease of that same major/minor/patch tuple.

## Runtime API 2.1 communication

API 2.1 adds injected renderer `client.events.on(localName, handler)`,
`client.dependency(pluginId)` and `client.background.call(localName, payload)`
alongside the existing `client.call`. Dependency IDs use the manifest's existing
strong/optional lists. Missing or inactive optional peers return `null`; retained
peers and calls from retired contexts fail with `plugin_unavailable`. The same
local names are used for self and declared peers. Background setup registers
awaitable methods with `ctx.rpc.handle`; `ctx.events` is plugin-local and
`ctx.hostEvents` explicitly subscribes to host events.

Components must renew subscription effects when their injected `client` changes.
The host replaces contexts on a real runtime publication or bridge restart,
reclaims methods/listeners/pending requests on teardown, renderer failure, and
main-frame document reload/navigation. Document ownership tokens prevent delayed
cleanup from touching successor registrations; in-page/subframe navigation leaves
contexts intact. `runtime.applied.changed` means a new runtime generation was
published, independently of the idempotent RPC response's historical `changed`
value. Same-generation retries, no-op saves, and role-only writes emit refresh
events with `changed: false`; retries from retired generations emit no event.
These refreshes leave communication contexts intact. Background request waits are
bounded and do not occupy backend RPC scheduling capacity. Method policies on
backend calls are unchanged. See [the plugin tutorial](plugins-tutorial.md#桌面-rpc事件与-ui)
for examples and delivery/error semantics. Packages using these additions must
require `runtime_api: ">=2.1.0 <3.0.0"`; the existing `client.call` signature and
Python exported dependency API remain compatible. This is cooperation under the
existing trust model, not a sandbox; the CSP and resource grants are unchanged.

## Renderer artifacts and dependencies

The plugin's own build emits browser ESM, with a default export (direct or
`export { name as default }`). CommonJS, `.js` with ambiguous format, TypeScript,
JSX source, empty modules, and missing default-export declarations are rejected.
The static check verifies extension, UTF-8, a lexical default export and absence
of CommonJS loading constructs. It is **not a full JavaScript parser** and does
not prove arbitrary JS syntax, imported module graphs or exported value types.
The renderer loader must parse the complete graph and validate the exports before
activation; resulting initialization errors are `FAILED`, not successful partial
activation. Cross-renderer rollback belongs to #262.

The default exports retain the current contribution ABI:

| Entry | Default export |
| --- | --- |
| `ui` | `{ pluginId, navPage?, settingsSection?, roleAssets?, roleSettings?, chatImageActions? }`, matching `PluginUiModule` |
| `background` | `{ pluginId, setup(ctx) }`, matching `PluginBackgroundContribution` |
| `surface` | `{ pluginId, surface: { component } }`, matching `PluginSurfaceModule` |

`pluginId` must match the manifest ID. UI and surface components receive the
existing host-injected props; background setup receives the existing background
context. Code must not assume Vite globs, host source-relative imports or a host
rebuild. A source package is built in the plugin's own repository.

React and React DOM are peers, never copied into a plugin's bundle. The renderer
ABI currently guarantees `19.2.0` for both (a compatibility floor rather than
probing developer `node_modules`); a host may explicitly advertise a newer peer
version via `HostRuntimeContract`. External resolution must use the host's single
React/React DOM instances, including their public subpaths such as
`react/jsx-runtime` and `react-dom/client`. No other bare npm runtime dependency is
part of v1. Plugins may use build tools in their own repository, but must not ship
or request installation of private npm/Python runtime dependencies. CSS is shipped
by the plugin and scoped to its own classes. Relative resource references must
stay inside the package; declared `assets` are validated as required files.

Python code may use the standard library, public Runtime API, local plugin code,
and **declared, host-provided** distributions. `host_dependencies.python` uses
normalized distribution names (for example `PyYAML`, not its `yaml` import name).
The default host inventory reads installed direct production dependencies from
`shiori-agent` distribution metadata, without importing them; development-only,
bundled plugin and incidental transitive packages are not public dependency APIs.
The desktop build preserves the host's distribution metadata and dependency
versions with PyInstaller's `--recursive-copy-metadata shiori-agent`. Other frozen
hosts without that metadata must supply their build inventory explicitly.
An unavailable declared dependency is `BLOCKED`. This validator does not install
anything or attempt to discover arbitrary dynamic imports. Authors must declare
the complete external dependency set; capability/dependency declarations are API
cooperation, not isolation of malicious code.

## Main-window UI loader (#213)

The desktop main window can consume `renderer.ui` as precompiled ESM and CSS at
runtime. For example, declare `entry: ui/dist/index.mjs` and
`css: [ui/dist/style.css]`; the directory name is not fixed. The plugin author
runs the build. The application carries no plugin compiler and does not invoke
the user's Node/npm installation. Externalize `react`, `react/jsx-runtime`,
`react-dom`, and `react-dom/client` in that build; bundle other browser libraries.
An import map resolves these peers to the same instances used by the host.

Only a unique, enabled `ACTIVE` workspace candidate receives a resource grant.
Main-process `plugins.list` responses contain the granted entry/CSS URLs alongside
the same authoritative state snapshot. Grants use `shiori-plugin:` URLs, retain
package-relative module chunks and CSS resources, and survive repeated list
requests. The resource handler rechecks package and resource realpaths, rejects
ungranted tokens and escapes, and serves only `.mjs`, `.js`, `.css`, `.png`, `.jpg`,
`.jpeg`, `.webp`, `.svg`, `.gif`, `.woff`, and `.woff2` files. Source files and
arbitrary filesystem URLs are not exposed through this protocol. CSP admits this
controlled scheme and the exact import-map hash; production adds neither
`unsafe-inline` scripts nor `unsafe-eval`.

Initial roster loading, bridge reconnection, `runtime.applied`, and plugin toggles
share one serialized refresh path. Disable/removal cleans this window's registry
entries and CSS. JavaScript module evaluation follows browser caching; replace a
plugin package and restart the application to load its new code.
Package identity and module URLs survive disable/re-enable for the app session;
changing its directory, version, or renderer declarations requires a restart.
The backend retains the approved startup file hashes, including chunks not yet
imported, and attaches them to the authoritative plugin roster. Main-process grants
first verify disk contents against those hashes; they never trust a newer local
baseline. Every resource response verifies the same hashes again. New or changed
scripts, CSS and assets are refused instead of mixing approved and unapproved content.
A failed import,
stylesheet, or export validation removes that plugin's partial UI and preserves
the original error as `UI FAILED` in plugin management and a renderer diagnostic.
Other plugins continue loading. The backend state stays separately visible;
this is not the cross-host activation transaction planned in #262.

Workspace packages start `UNTRUSTED`. Settings → Plugins offers **信任…** only for
valid, non-conflicting packages. The dialog shows the package name, version and
actual path, and explicitly warns that plugin code receives the same permissions
as Shiori. Cancel writes nothing. Confirm persists approval and displays **待重启**;
only the next application launch can activate it. Restarting the bridge within
the same desktop session does not activate a newly approved package.

The host atomically stores approval in `private_runtime/plugin-trust.json`, outside
plugin directories. Approval binds the candidate path and a SHA-256 identity of
the real package directory, all published filenames and bytes. Confirmation
rechecks static validation, ID conflicts and content against the displayed
fingerprint; changed or replaced candidates must be reviewed again after restart.
Any published source, manifest, JavaScript, CSS or asset change invalidates trust.
Trust does not modify the separately persisted enabled/disabled preference.

Trust snapshots reject package-content symlinks/junctions, including contained
links, rather than expanding the approved tree through aliases. Only regular
`.pyc` and `.pyo` bytecode files are excluded; other content inside `__pycache__`
or directories with cache-like names remains fingerprinted. To keep bytecode from being
an unapproved execution path, external Python namespaces use a source-only loader:
entry and lazy relative imports compile only verified snapshot bytes. New modules,
bytecode-only modules and native extensions cannot bypass that namespace boundary.
Every settings generation rechecks the original approved fingerprint before
re-importing an external backend. Finder lifetime follows the plugin effect scope.

Manual trust is implemented here; zip install, update and uninstall workflows
remain in #216. Bundled source UI, external background entries, and external
surface entries retain their existing paths in this slice.

Focused Electron verification builds a separate test renderer, uses a fixture
`ACTIVE` roster, and checks actual `file://` ESM loading, shared React hooks,
relative chunks, CSS, failure isolation, disable/re-enable cleanup, protocol
rejection and CSP rejection. It does not prove workspace trust. Run after the
desktop main/preload build:

```powershell
pnpm exec tsx --tsconfig apps/desktop/renderer/tsconfig.json apps/desktop/tests/plugin-ui/electron.e2e.ts
```

The real workspace flow uses the production main process, preload and backend in
an isolated QA home. It verifies cancel, confirmation, pending status across bridge
reconnection, app restart activation, React hooks and RPC, content-change approval,
and removal without residual UI, CSS or plugin errors. Screenshots are retained in
`.test-tmp-root/plugin-trust-real-*`. This uses the repository `.venv` by default;
set `SHIORI_QA_RUNTIME_EXE` to an existing frozen runtime executable to verify that
runtime with the same test bootstrap without changing production interpreter selection.

```powershell
pnpm exec tsx --tsconfig apps/desktop/renderer/tsconfig.json apps/desktop/tests/plugin-ui/trust.e2e.ts
```

## Paths, archive limits and lifecycle

Paths use canonical relative `/` segments. Absolute paths, drive/UNC paths,
backslashes, `.`/`..`, empty segments, Windows alternate data streams, reserved
device names, trailing dots/spaces and control characters are rejected on every
platform. Every declared file and `manifest.yaml` must resolve to a regular file
inside the package root; an escaping symlink/junction is rejected. Zip member
names are checked before temporary extraction, including their original spelling
before Python's Windows normalization. Archives reject links, special files,
encryption and case-colliding member paths. Limits are 4,096 members and 64 MiB
uncompressed. Validation never installs or modifies a workspace package.

Host state vocabulary extends the existing lifecycle enum:

| State | Meaning / next boundary |
| --- | --- |
| `UNTRUSTED` | manifest inspectable, no code allowed until explicit trust |
| `BLOCKED` | static contract/runtime/dependency failure, retry after correction |
| `FAILED` | import/setup or contribution initialization failed; reclaim started resources |
| `CONFLICT` | multiple candidates claim one ID; select none until resolved |
| `RESTART_REQUIRED` | an accepted code-directory change awaits application restart |
| `DISCOVERED`, `DISABLED`, `LOADING`, `ACTIVE`, `UNLOADING`, `DISPOSED` | existing runtime lifecycle |

Workspace discovery (#211) reports `UNTRUSTED` until the exact content has a valid
approval from a previous app session, and marks every candidate with a duplicate
manifest ID `CONFLICT`. Both states prevent execution and enable actions.
`RESTART_REQUIRED` remains the code-change boundary for downstream hosts; manual
approval exposes a separate pending-restart flag while backend state stays untrusted.
Enabled/disabled preferences remain separate from code
version/restart state. Updates must not silently re-enable disabled plugins.

Static rejection raises `PackageContractError` with `diagnostic.to_dict()`:

```json
{
  "code": "missing_file",
  "stage": "validation",
  "field": "renderer.surface.entry",
  "reason": "Original file-system error or precise contract rejection",
  "path": "renderer/surface.mjs",
  "state": "BLOCKED"
}
```

The host snapshot supplies identity, directory and lifecycle state. `code` is
machine-readable; `field` identifies the declaration, `reason` retains the cause
and `path` identifies the artifact when applicable. Kernel `states()` and
`plugins.list` retain validation diagnostics, including malformed opt-in manifest
candidates. Missing or inactive strong plugin dependencies use stage `dependency`,
field `dependencies[index]`, and code `missing_dependency` or
`dependency_unavailable`; their original dependency error is retained in `reason`.
Runtime failures retain their original `error`; they do not reuse a static
`BLOCKED` diagnostic. A passing validator alone does not mean trusted,
active or ready to run in every renderer.

## Independent example and validation

Copy `tests/fixtures/external-plugin/` to a directory outside Shiori. Its pinned
pnpm/esbuild build compiles TSX/TS into ESM, externalizes React peers, copies its
backend/CSS/assets and produces the package root. No host npm package, Vite build,
private path or source checkout is needed to **build** it. See the fixture README
for commands and how to validate its directory/zip from a host environment.
