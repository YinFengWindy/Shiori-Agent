# Windows packaged external-plugin acceptance

This procedure launches the production `Shiori.exe`, requires `app.isPackaged`
and the expected application version, and loads `resources/app.asar` plus the
bundled PyInstaller sidecar. `tests/plugin-ui/trust.e2e.ts` remains a development
Electron test; its bootstrap/runtime overrides are not packaged evidence.

## Build an isolated candidate

Run from a fresh issue worktree. Confirm the resolved runtime/work/output paths
are below that worktree before running builds that remove old build directories.
Do not publish a tag or Release to perform this acceptance.

```powershell
uv sync --frozen --dev
pnpm install --frozen-lockfile
$env:SHIORI_RELEASE_OUTPUT = Join-Path (Get-Location) 'release/installer'
$env:SHIORI_RELEASE_VERSION = '0.3.0-rc.1'
node apps/desktop/scripts/release-manifest.mjs runtimeOutput
node apps/desktop/scripts/release-manifest.mjs pyinstallerWork
node apps/desktop/scripts/release-manifest.mjs installerOutput
pnpm --filter shiori-desktop run package:win
pnpm --filter shiori-desktop run verify:package
```

Copy `tests/fixtures/external-plugin/` to a new directory outside the repository.
Follow its README to install its own build dependency and generate all six ZIPs.
The host is built once; v1/v2/v3 and invalid fixture versions are built separately.
The runner never rebuilds the host while installing/updating a plugin.

## Automated packaged run

Choose a fresh output directory with space for one disposable unpacked app copy
and a temporary resource copy. The original release artifact is never modified.

```powershell
pnpm exec tsx --tsconfig apps/desktop/tests/plugin-ui/packaged.tsconfig.json apps/desktop/tests/plugin-ui/packaged.e2e.ts --app C:/candidate/win-unpacked/Shiori.exe --fixture D:/independent-fixture/artifacts --output D:/qa/run-1 --version 0.3.0-rc.1
```

The runner uses real production windows, bridge, file-import staging, dialogs,
trust records, restart transactions and resources. It substitutes only Electron's
native file chooser result; OS chooser interaction requires the manual step below.
`SHIORI_DESKTOP_WORKSPACE` selects the complete workspace/config root and
`SHIORI_DESKTOP_USER_DATA_DIR` selects the Electron device profile. The profile is
set before the single-instance lock. Do not assume `USERPROFILE` changes Electron's
home path: on the tested Windows environment it does not.

The run records each application identity and artifact hash, actual UI/bridge
observations, screenshots and `results.json`. It covers cancellation before code
execution, four entries, persisted timer progress, tool/RPC/subscription/UI/CSS/
surface cleanup, hot reenable, staged updates, corruption after confirmation,
rollback, default retained data and explicit reinstall confirmation, duplicate
IDs, API mismatch, missing backend entry, renderer failure, and replacement of a
QA artifact's resources while preserving workspace bytes. Resource replacement
uses the same candidate bytes; it proves storage separation, not an NSIS version
upgrade, updater download or operating-system installation/uninstallation.

Failed runs retain their evidence and isolated directories. `failure.txt`,
`failure-dom.txt`, `renderer-errors.json`, profile `desktop-diagnostics.log` and
workspace `private_runtime/plugin-operations/` identify the boundary that failed.
A passing early phase is not a successful complete lifecycle run.

## Native desktop observation

Use a separate fresh workspace/profile and the verified candidate executable:

```powershell
$env:SHIORI_DESKTOP_WORKSPACE = 'D:/qa/manual/workspace'
$env:SHIORI_DESKTOP_USER_DATA_DIR = 'D:/qa/manual/profile'
& 'C:/candidate/win-unpacked/Shiori.exe'
```

Seed only an isolated `config.toml` with empty LLM registrations and disabled
maintenance/desktop_pet if no providers are configured. In Settings → Plugins,
click **安装插件 ZIP**, select the outside-built ZIP in the actual OS chooser,
inspect/cancel the trust dialog, then confirm and observe pending state. Exit via
the actual tray **退出** item; closing the window merely hides it. Relaunch with
the same two environment variables. Observe the fixture page and surface, click
both RPC buttons, disable/enable, update to v2, and verify uninstall/reinstall
confirmation with the retained sentinel. Keep manual screenshots/notes separate
from automated chooser-substituted evidence. An automated `ElectronApplication`
uses its ordinary `close()` for orderly shutdown; no production test IPC exists.

Record OS/architecture, Node/pnpm/Python/Electron versions, source revision, app
version, installer/executable/app.asar/fixture hashes, isolated paths, commands,
observations, and untested portions. Local Node 24 results do not claim the release
workflow's Node 22 environment. Existing release CI gates remain required.

## Recorded candidate: 2026-09-18, 0.3.0-rc.1

The automated run below passed against the candidate built from base
`138841a693e80e76b097db45b79b02588ce58ef4` plus the #263 implementation changes.
The artifact hashes, rather than an earlier run's partial success, identify this
exact build. No tag or Release was published. Native observation is recorded
separately by the delivery owner after this automated run.

Environment: Windows 11 Home China 10.0.26200 x64; Node 24.19.0; pnpm 10.33.0;
Python 3.12.9; PyInstaller 6.22.2; Electron 43.4.1. The host source worktree is
`C:/Users/yufeng/.codex/worktrees/issue-263-packaged-plugin/Shiori`.
The independent fixture and all disposable runs are outside that tree at
`D:/Coding/Shiori-qa-263-iuvi8nxb`. Fixture installation used its own
`pnpm install --ignore-workspace`; its bundles retain host React peer imports.

| Artifact under worktree `release/installer/` | SHA-256 |
| --- | --- |
| `Shiori Setup 0.3.0-rc.1.exe` | `90758967a8c27d338bcfe0cc74d805306a8204ca39f91865a4405a2b3c50de24` |
| `win-unpacked/Shiori.exe` | `e8f2ebd675218818ca2c93566c6cfd2f3bbd9a12c42f8f5f7792c393a4ae0b93` |
| `win-unpacked/resources/app.asar` | `448ecb8fcfe792e8f766a14908d22940a868ec9d39a5f05d37afead8aed40bde` |
| `win-unpacked/resources/runtime/shiori-runtime.exe` | `2d9c50e89e673e52260f709f643d12d520c8ad0280249c89b04391d2380d2928` |

The final command was run from that worktree:

```powershell
pnpm exec tsx apps/desktop/tests/plugin-ui/packaged.e2e.ts --app C:/Users/yufeng/.codex/worktrees/issue-263-packaged-plugin/Shiori/release/installer/win-unpacked/Shiori.exe --fixture D:/Coding/Shiori-qa-263-iuvi8nxb/fixture/artifacts --output D:/Coding/Shiori-qa-263-iuvi8nxb/run-5 --version 0.3.0-rc.1
```

`run-5/results.json` contains 28 timestamped records, from 08:55:13 to 08:56:20 UTC,
including ten genuine packaged launches and a final `complete` record. Its first
record includes every ZIP hash and isolated executable/workspace/profile path.
The following observations passed within that one run:

| Boundary | Observed result |
| --- | --- |
| Invalid API and missing backend entry | Each diagnostic names the specific incompatibility/missing path; no fixture RPC or roster entry appears. |
| Initial install | Cancelling executes no fixture; confirmation queues installation; restart enables all four entries. |
| Active fixture | Backend tool executes; UI and surface call RPC; UI/background receive the emitted event; a real role deletion invokes the backend subscriber; persisted timer ticks advance. |
| Hot stop and start | RPC, tool, role subscriber, timer, UI, CSS in every renderer, and surface are removed; enabling again restores all four entries without a host rebuild. |
| Valid update | v1 remains active while v2 is staged; restart activates v2. |
| Corrupt confirmed update | Tampering with the staged v3 backend retains v2 and its sentinel after restart, with `package_operation_error` visible. |
| Uninstall and reinstall | The default unchecked delete-data option retains the sentinel; cancelled reinstall cannot access it; confirmed reinstall remains inactive until restart, then reads it. |
| Resource replacement | Only the disposable application's resources are replaced; workspace manifest and data bytes remain unchanged before restart, then v2 and its sentinel work. |
| Duplicate ID | Both candidates report conflict; RPC, UI and surface stay unavailable. |
| Renderer initialization error | The deliberate v4 UI error produces `renderer_ui_failed`; backend tool/RPC/subscription, started background resources, styles, UI and surfaces are rolled back. |

Evidence includes `run-5/*.png`, `run-5/results.json`,
`run-5/profile/desktop-diagnostics.log`, and command logs under
`C:/Users/yufeng/AppData/Local/Temp/shiori-263-evidence/`.
The main window's captured `pageerror` list is empty. Desktop diagnostics also
contain scope-replacement cancellation messages (`插件通信已处置`) and the
updater's `No published versions on GitHub` response; these are retained, not
represented as an entirely error-free log. The deliberate renderer failure is
also recorded there. Native chooser use and NSIS installation/version upgrade
are not established by this automated run.

Two product defects were reproduced before the final candidate:

- `run-2/profile/desktop-diagnostics.log` records the external surface failing to
  resolve `react`. Peer installation formerly ran only in the main UI document.
  The shared DOM loader now initializes immutable host peers and the import map
  once in each UI/background/surface document; a focused test verifies independent
  documents and repeat calls.
- `run-4/failure.txt` records reenable remaining pending on the background renderer.
  Its cached module registration prevented acknowledgement of a new activation
  token. Background admission now restores CSS and confirms each activation while
  keeping the immutable registration available for effect teardown. A focused
  test proves disable/reenable and token changes without duplicate imports.

Those failed runs used earlier hashes and are retained only as defect evidence.
`run-1` exposed a harness screenshot timeout and `run-3` an overly early read of
the prior diagnostic; the harness now uses Electron window capture and waits for
the precise expected diagnostic. They are not counted as successful acceptance.

Local validation: 25 runtime-path/peer/background/surface tests plus 11 UI and
activation callers passed; 12 packaging tests and 45 backend contract/archive/main
tests passed. `pnpm lint` passed with one existing `RoleAssetCategoryGroups.tsx`
hook warning; `pnpm typecheck`, explicit packaged-runner and fixture TypeScript
checks, fixture Pyright (0 errors/warnings), Black (962 files), Ruff, production
desktop/runtime/NSIS builds and `verify:package` passed. The default desktop type
check does not include the acceptance runner or independent fixture, so their
separate `tsconfig.json` checks are required. No full local suite was run.

The native follow-up uses `D:/Coding/Shiori-qa-263-iuvi8nxb/manual/launch.ps1`,
which sets separate `manual/workspace` and `manual/profile` directories and
launches the same frozen candidate. All six final ZIPs are in `fixture/artifacts`;
`external_demo-1.0.0-valid.zip` is the initial install and
`external_demo-2.0.0-valid.zip` is the update. Use the tray exit before relaunching.

### Native observation completed before interruption

The delivery agent used Windows accessibility/input controls against the same
candidate and `manual/workspace` / `manual/profile`. It opened Settings → Plugins
→ Installed, clicked **安装插件 ZIP**, entered the outside-built v1 ZIP path in
the actual Windows **打开** dialog, and observed **安装插件** showing
`external_demo`, `1.0.0`, the ZIP filename, the isolated workspace destination,
restart requirement, and full-trust disclosure. Clicking **信任并安装** produced
the visible **待重启 · 安装** row. These actions did not substitute the chooser.

The isolated process tree was then terminated and relaunched to continue the
native check; this is not evidence of a normal tray exit. Before observing the
restarted window, the user pressed physical Escape to stop computer control.
No further desktop input was issued. Native post-restart four-entry interaction,
hot toggle, update, and uninstall/reinstall observation remain unfinished. Their
automated packaged coverage above is complete, but is not relabeled as human or
native manual acceptance. #263 remains open pending that follow-up.

### Main integration: plugin details management

PR #322 head `6cc18af6` was integrated with main
`f3a0f5fd2f8364e8b631ad380544f6d3638b3400` (#326–#328). The packaged runner now
opens the `external_demo` title's details dialog, chooses **从 ZIP 更新** or
**卸载插件**, and explicitly closes the restored details after the nested
confirmation. It also retains Electron process stderr with the other run evidence.
The production UI, runtime protocol and independent fixture were not changed for
this adaptation. No native desktop control was resumed.

Before building, the resolved runtime, PyInstaller work and integration output
directories were verified to be children of the issue worktree. Only the desktop
was rebuilt with `pnpm build:desktop`; the frozen Python runtime was reused.
The unpacked production application was packaged from `apps/desktop` using:

```powershell
$env:SHIORI_RELEASE_OUTPUT = 'C:/Users/yufeng/.codex/worktrees/issue-263-packaged-plugin/Shiori/release/integration-installer'
$env:SHIORI_RELEASE_VERSION = '0.3.0-rc.1'
node node_modules/electron-builder/cli.js --projectDir . --config.directories.output=C:/Users/yufeng/.codex/worktrees/issue-263-packaged-plugin/Shiori/release/integration-installer --config.extraMetadata.version=0.3.0-rc.1 --win --x64 --dir --publish never
```

This preserves the standard asar and `afterPack` checks. It produces no new NSIS
installer. The original `release/installer` candidate and run-5 evidence remain
unchanged; this integration is identified separately:

| Artifact under `release/integration-installer/win-unpacked/` | SHA-256 |
| --- | --- |
| `Shiori.exe` | `453463d263e2f13a0912e404088d8c93c732d230bd35b92db3e579018ede0cb4` |
| `resources/app.asar` | `662e5b2f683f661985f4baa785b584ae99f125b1f048753af63278fa1b8671a4` |
| `resources/runtime/shiori-runtime.exe` | `2d9c50e89e673e52260f709f643d12d520c8ad0280249c89b04391d2380d2928` |

The complete automated integration run is
`D:/Coding/Shiori-qa-263-iuvi8nxb/run-integration-2/results.json`: all 28 records
passed, ending at 10:27:09 UTC on 2026-09-18. It verifies the real packaged entry,
version `0.3.0-rc.1`, isolated profile/workspace, updated details controls, and the
same lifecycle assertions as run-5. All six fixture ZIP hashes match run-5. The
main-window page-error list is empty; `process-stderr.log` is retained. Command
logs use the `integration-` prefix in the existing evidence directory.
The `--dir` artifact has no `app-update.yml`; its automatic update check logs
`ENOENT` for that metadata. This run does not validate updater distribution.

The first attempt, `run-integration`, is retained as a failed run. Following
resource replacement, the background RPC reported ticks 3/events 1 while its file
stayed at ticks 2/events 0 and a `.tmp` file contained ticks 3. Persistence polling
timed out. This suggests a file publication problem, but the original run did not
capture process stderr, so no specific Windows sharing/rename error is proven.
The same package and unchanged fixture passed the full second run after adding
stderr capture, without relaxing assertions or modifying production storage.
The intermittent first failure remains a limitation of this evidence.

Integration validation passed: 12 plugin details/management/package-controller
tests, `pnpm lint` (the existing hook warning only), `pnpm typecheck`, the runner's
explicit TypeScript config, desktop build, packaged layout verification, and the
complete second packaged run. No Python source or fixture change required a new
backend build or Python test run. The native follow-up above remains unfinished
under #263; this automated run does not complete it.
