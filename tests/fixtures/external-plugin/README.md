# Independent external lifecycle fixture

Copy this folder outside Shiori before building. It requires Node 22+ and pnpm
10.33.0; esbuild 0.25.12 is its own build dependency. No host source, Vite glob,
private runtime dependency or host rebuild participates in a plugin update.

```powershell
pnpm install --ignore-workspace
pnpm build --version 1.0.0
pnpm build --version 2.0.0
pnpm build --version 3.0.0
pnpm build --variant incompatible
pnpm build --variant missing-entry
pnpm build --version 4.0.0 --variant renderer-failure
```

Each build produces `artifacts/external_demo-<version>-<variant>/` and a deterministic
ZIP beside it, with `manifest.yaml` at its root. The build prints the archive's
SHA-256. React and React DOM remain host peers. `zip.mjs` uses Node's standard
library; it stores regular files with stable timestamps and no enclosing folder.
`src/contract.d.ts` describes only the injected API subset used by this independent
example; it imports no Shiori types. Host validation is separate from building:

```python
from pathlib import Path
from agent.plugin_host.package_archive import validate_package_zip

package = validate_package_zip(Path("D:/independent-example/artifacts/external_demo-1.0.0-valid.zip"))
assert package.manifest.id == "external_demo"
```

Backend setup registers a tool, namespaced RPCs and a real `RoleDeleted` subscriber.
The UI exercises backend, background and event communication. The background owns
a timer, a persisted observation record, an RPC handler and a visible surface;
the surface uses host React and calls backend RPC. `Save retained data` writes the
sentinel `retained-user-value` to the plugin KV. A teardown audit checks that the
registered tool was removed. No network, model or paid API is called.

The incompatible and missing-entry variants fail static admission. The renderer
failure variant has a valid package contract but throws a specific error while
its UI module initializes. Corrupt-after-confirmation update coverage modifies
only a staged QA copy of the valid v3 package; the distributed ZIP stays intact.

The packaged runner and manual steps are documented in
`docs/_handbook/packaged-plugin-acceptance.md` in the host repository. Building or
validating this fixture alone does not establish packaged application acceptance.
