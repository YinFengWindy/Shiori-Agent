# Shiori SDK

`@shiori/sdk` and `shiori-sdk` are the TypeScript and Python distributions of the
same plugin contract. Both are version **3.1.0**, with Runtime API **3.1.0**.
They are built locally and in CI; this repository does not publish them to npm or PyPI.
External plugin manifests declare `runtime_api: ">=3.0.0 <4.0.0"`, or
`">=3.1.0 <4.0.0"` when they use the 3.1 lifecycle additions (`AfterTurnCtx`,
`PHASE_SLOTS`, `require_phase_slot`, `LifecycleModule.requires` / `produces`). The host rejects
an incompatible range with an `incompatible_runtime` diagnostic before executing
the plugin backend. Version 3 requires rebuilding existing renderer imports.

## TypeScript

The main entry exports plugin contracts, components and helpers. `/contract`
contains React/DOM-free types; `/host-internal` is reserved for host code; `/testing`
provides independent UI fakes and a DOM harness and is never a runtime peer.
TypeScript consumers of `/testing` use `@types/node >=26.6.3`, declared as an
optional type peer because happy-dom exposes Web Streams types from that version.
This is a declaration requirement, not a change to the runtime Node requirement.
Workspace consumers resolve source; `pnpm --filter @shiori/sdk pack` builds an ESM
tarball with declarations and external React peers. The host import map provides
the same main entry to precompiled plugins. Only the main entry belongs in a
plugin's production peer imports.

## Python

The wheel contains contracts and pure values, without a dependency on the host.
The core lifecycle surface includes `PluginRuntimeContext`,
`LifecycleFrame`, `LifecycleModule`, `LifecycleCapability`, `EventsCapability`,
`Dispose`, `EventHandler`, `AfterStepCtx`, `AfterReasoningCtx` and `ResponseMetadata`.
The host owns phase execution, storage, capability authorization and cleanup.
`setup(ctx)` receives its declared capabilities; undeclared access raises
`CapabilityNotGranted`. Runtime injection is checked through a static
`PluginSetupContext` without the legacy context's dynamic attribute fallback.
Typed setup contexts also cover memory, hooks, commands, diagnostics, role/model
and process services, channels and accounts. Their capability protocols and
independent testing fixtures are documented below; host service implementations
remain in the host.

```python
from shiori_sdk import PluginRuntimeContext
from shiori_sdk.lifecycle import LifecycleFrame

class TraceStep:
    slot = "example.trace"
    requires = ("after_step.copy_input", "step:ctx")
    produces = ("step:telemetry:example",)

    async def run[FrameT: LifecycleFrame](self, frame: FrameT) -> FrameT:
        frame.slots["step:telemetry:example"] = True
        return frame

async def setup(ctx: PluginRuntimeContext) -> None:
    ctx.lifecycle.contribute("after_step", [TraceStep()])
```

Install `shiori-sdk[testing]` for pytest/pytest-asyncio, `sdk_context`,
`FakePluginContext`, `FakeLifecycle`, `FakeEvents`, `FakeFrame`, package staging,
bridge request helpers and shared test TLS contexts. Fakes store only test values
in memory; they never open host persistence. `sdk_context` reads the nearest
`manifest.yaml` above the test file (within the pytest rootdir; override the
`sdk_plugin_dir` fixture otherwise) and grants only its declared `capabilities`,
validated against the host's `KNOWN_CAPABILITIES`, so undeclared access raises
`CapabilityNotGranted` as in the host. The manifest is only read: `plugin_dir`
is an isolated temporary directory, and bundled files are package assets. `FakeLifecycle`
records modules for explicit execution and rejects slots outside
`shiori_sdk.lifecycle.PHASE_SLOTS` like the host; it does not simulate the host
phase dependency sorter.
HTTP response contracts and tolerant JSON helpers declare httpx/json-repair as
runtime dependencies. pytest-asyncio and test fixtures remain optional.
The base wheel can coexist with pytest without the testing extra: unrelated tests
collect and run normally. Requesting `sdk_context` without the extra reports the
installation requirement. Optional fixtures load only when their dependencies exist.
SDK-only tests never start `AppRuntime`. Real host integration fixtures live in
`shiori_host_testing`, including its real workspace-backed memory fake. That
private development package is never installed in plugin or SDK isolation.

## Maintenance and validation

`python/shiori_sdk/_version.py` is the version source. Python packaging reads it
directly. After changing it, run `node scripts/sync_sdk_version.mjs` from the root
to update npm metadata, then update consumer constraints and locks. Lint and the
npm build both run the consistency check.

```sh
pnpm lint
pnpm typecheck
pnpm run sdk:smoke
uv run python -m scripts.verify_sdk
uv run python -m scripts.verify_plugin_tests
uv run python -m scripts.check_sdk_imports
```

The artifact probes install tarball/wheel non-editably outside the checkout. The
wheel probe first collects/runs an unrelated test with only the base SDK and pytest,
checks the missing-extra diagnostic, then installs the extra and runs all SDK tests.
The plugin probe discovers all plugin suites (currently all 20 baseline plugins),
builds ordinary wheels from external copies, and installs only each target's
declared dependency closure. Every `shiori-*` package comes from the local
wheelhouse with `--no-index --no-deps`; a missing local wheel fails instead of
falling back to an index. Third-party requirements are installed separately and
`uv pip check` verifies the result. No host or default-memory package is injected.
Each suite and its awaited failure probe owns a separate pytest temporary directory.
Provenance checks run before and after the suite, checking host absence, all
distribution origins, editable installs, repository path injection and SDK versions.
An execution probe starts before initial conftests and rejects implementation code
from every staged target/dependency tree or the original checkout (including SDK
sources), even when a temporary module alias is removed before the suite ends.
Installed entry origins and hashes cover the target's complete declared plugin closure.

The import guard has no exemptions. It checks SDK and plugin Python sources,
tests, stubs and packaged testing helpers, including TYPE_CHECKING, import aliases,
literal/string-composed dynamic imports, string patch targets, `importlib.resources`
and `pkgutil` resource access (attribute, alias or literal `getattr` forms), and host
resource paths built from `__file__` (`Path`/`pathlib.Path`, `os.path.dirname`/
`split`/`join`, literal `*[...]` arguments, folded string concatenation) or from the
working directory starting with a host top-level entry (actual backend packages,
`apps/`, `packages/`, `tests/`). Path values are followed through names bound in the
same module only; paths passed through attributes or call results (for example
`self.root.parents[3]`) are left to external execution.
Exclusions are judged relative to the scanned package: virtual environments,
caches and a plugin's root-level `build/`/`dist/` outputs; package-internal
directories such as `backend/build/` are scanned wherever the checkout lives.
Host roots follow the actual backend package/module tree.
SDK dependencies cannot point to concrete plugins. Declared public sibling plugin
dependencies remain valid. This static guard is complemented by external execution;
it does not claim to sandbox arbitrary Python.

CI separates all-plugin isolation, SDK artifact tests, host integration and installed
host-resource checks. Existing renderer and Windows process lifecycle jobs remain.



## Memory engines

`shiori_sdk.memory.engine` owns memory requests, results, scopes, tool profiles and
`MemoryEngine`. `memory.events` and `memory.committed` own shared ingestion,
consolidation and committed-turn values; implementations and SQLite stay outside SDK.
Pure semantic pagination/filter declarations live in `memory.requests`; each engine
owns its status vocabulary and removes private vector/hash fields from responses.

A memory package exposes `MemoryPlugin.build(MemoryPluginBuildDeps)`,
`ensure_workspace_storage(...)` and `validate_transition(...)` from its
`backend/memory_plugin.py`. Build inputs contain resolved `MemoryBuildConfig`
(model selection and embedding credentials), a `ModelProvider`, bounded HTTP
requester, typed queued events, a skill-name callback and narrow role/storage ports.
No full host Config, RoleStore, provider implementation or Markdown service crosses
this boundary. The storage port retains host migration receipts, atomic publication
and live-database leases. Compatibility failures use
`MemoryStorageIncompatibleError.to_details()` for the settings recovery hint.

Construction must register every allocation with `deps.resources.register(value,
cleanup)` before allocating the next resource. Call `transfer()` only after the
engine is complete and return its records in `MemoryPluginRuntime.resources`.
The caller retains an outer construction cleanup scope until all host assembly
succeeds, then consumes those exact callbacks at shutdown (including opaque values
with no close method). Returned callbacks run once; cleanup continues in reverse
order if one callback fails. A direct build caller supplies and owns that scope.

Setup plugins declaring `memory` and `rpc` use `MemoryPluginContext`: shared
Markdown reads, role existence/permissions, storage and current engine are injected,
while RPC registration remains plugin-owned. `BeforeTurnObservation` exposes only
inspection fields; `AfterToolResultCtx` is the shared result event. Standalone tests
can use `FakeMemoryPluginContext`, `FakeMemoryRoles`, `FakeMemoryStorage` and
`FakeBuildResources`; real migration and runtime assembly remain host integration tests.


## Tool policies, commands and observation

`shiori_sdk.tools` owns `Tool`, `ToolResult` and result normalization; `tool_hooks`
owns `PreToolCtx`, `HookOutcome` and registration. Policies remain in plugins.
`HookOutcome(finalize=True, decision="deny")` requests host summarization while
ordinary denial leaves the existing execution flow intact. `HookPluginContext`
provides granted config, workspace and hook registration.

Before-turn command modules accept a `CommandFrame`, read its immutable
`CommandInput`, and call `frame.abort_command(reply)`. The host constructs the
ordinary abort result, retaining channel, timestamp and context scope and skipping
retrieval/model calls. `last_consolidated` is memory progress, not model compaction.
`SessionUndo` supplies an atomic undo result and invokes a memory source resolver
before deleting messages. The optional `MemoryUndo` extension supports dry-run and
real cleanup. A command resolves it from the current memory engine; engines lacking
that extension keep working without memory undo. `CommandPluginContext` also
provides command-menu registration and current declared dependency exports.

Observe uses `ObservePluginContext` with `background`, `storage` and `diagnostics`.
The migration port is shared with memory construction. The host owns receipt/lease
handling, the active error session, installed package and external plugin code roots,
and the process-global hook stack. The plugin owns fingerprinting, deduplication,
flush and SQLite. Register collector cleanup before installing global hooks; stop
subscriptions before final flush, then cancel retention and writer in reverse order.
Source checkout depth is never a plugin contract.

Status commands declare `observe` as an optional manifest dependency and resolve
its public `recent_cache_turns` export for each command. Unload yields an unavailable
reply; reload uses the new export. Consumers do not inspect Observe's database.

`testing.extensions.FakeExtensionContext`, `testing.hooks.FakeToolHooks`,
`testing.commands.FakeCommandFrame` / `FakeSessionUndo` and
`testing.diagnostics.FakeDiagnostics` provide independent contract doubles.
Diagnostics fakes record callbacks without modifying process-wide handlers. Global
hook restoration and real lifecycle ordering stay in host integration tests.


`shiori_sdk.storage.plugin_data_dir` and `PLUGIN_DATA_DIRNAME` own the pure canonical
private-data layout and portable plugin-ID validation; host migration and SDK fakes
use the same helper. `PrivateStorage.migrate_data` returns the authoritative target.
Observe passes that resolved database path to both writer and public telemetry reader,
so an injected storage root remains consistent and reads never create storage.

## Role, generation and native services

`plugin_services.ServicePluginContext` describes statically checked setup inputs.
Properties require the corresponding manifest grant; the context does not grant
access merely because the interface declares a property.

| Capability | Contract and ownership |
| --- | --- |
| `roles` | Detached role snapshots, explicit asset resolution/adoption and opaque role-extension transactions. The host keeps its canonical RoleStore and write lock. |
| `models` | `async with ctx.models.activate(role_id, "chat" or "vision")` holds the host-selected provider/model snapshot across awaited work. No runtime registry or full Config is exported. |
| `sessions` | Session metadata, original media provenance, atomic image replacement and its host-owned desktop projection. |
| `http` | `HttpClient` uses the injected external transport and its default retry/budget policy. Memory's bounded `HttpRequester` remains separate. |
| `background` | `spawn` owns scoped tasks; `spawn_runtime` additionally retains the calling runtime generation until task completion. Both cancel and join outstanding work on unload. |
| `processes` | Creates explicit MCP sessions and owned child processes through the host's existing McpClient/owned_spawn/WindowsJob implementations. The SDK contains no process implementation. |
| `resources` | Supplies source/frozen resource roots and shared emoji paths; plugins do not guess checkout depth. |
| `tool_turn` | Returns the current host turn identity and awaited ownership finalizers. Model arguments cannot forge it. |
| `runtime` | `was_active` and `on_drain` preserve accepted work during generation replacement. |

`Roles.read_scope()` keeps a plugin's multi-read namespace reconciliation atomic
against canonical role edits. Plugins retain their schemas and policies; only
host storage operations cross this boundary. `PrivateStorage.migrate_data`
returns the authoritative directory and is mandatory when constructing plugin
catalogs. Neither plugins nor SDK fakes recreate the host's migration owner.

Shared prompt-section, scene-observation, RPC-error and MCP values have one SDK
definition. `files`, `media`, `errors` and `redaction` contain standalone helpers
operating on explicit values/paths. Native discovery, HTTP transport, role/session
storage and runtime leases remain host-owned.

`testing.service_context.FakeServiceContext` composes independent role, session,
tool, HTTP, resource, process, RPC and task fixtures. Native calls fail until a
test explicitly supplies their result. Plugin policy tests execute with only the
SDK and declared sibling dependencies (Story → NovelAI; Meme → Citation).
Individual fixtures live in their owning `testing.tools`, `testing.storage`,
`testing.sessions`, `testing.resources`, `testing.models`, `testing.http`,
`testing.runtime` and `testing.scene_observations` modules; the context only
assembles them. Role draft writers and covariant read-only projectors are defined
once in `shiori_sdk.roles` and used by both the host and independent fixtures.
Actual kernel ordering, role saves, session media adoption, runtime lease
retention, screen/desktop-pet integration and Windows Job cleanup remain in host
tests. PR CI includes a dedicated Windows process-lifecycle job.

Desktop pet also consumes `roles`, `storage`, `tools`, `rpc` and typed
`role_events.RoleDeleted` through this context. Sprite packages, role selection,
exclusive visibility and asset reconciliation remain plugin policies. Host
integration tests exercise canonical role locks, atomic saves, migration receipts
and kernel replacement with those public capabilities. `rpc.register` supports
`admission_exempt=True` for bounded controls that must remain reachable while
ordinary admission pauses; desktop-pet bubble dismissal uses this flag.
Pure timestamp/path helpers are defined once in `shiori_sdk.values`.

## Channel and account contracts

Channel plugins use `shiori_sdk.channels.context.ChannelPluginContext`; transport startup receives `shiori_sdk.channels.ChannelContext`. Account values/rules/targets live in `shiori_sdk.accounts`, message values in `shiori_sdk.messages`, stream events in `shiori_sdk.channel_events`, and provenance/quote helpers in `shiori_sdk.channels.message_source` and `reply_context`. The host injects intake, routing, attachment storage, HTTP and avatar services; it retains lifecycle and cache policy.

Declare `processes` for native children. `Processes.popen` is the synchronous counterpart of `spawn`, returning a process and an optional `ProcessOwner`; only the host implements OS ownership. QQ keeps NapCat installation, private profiles, QR codes and OneBot policy. Independent testing uses shared `FakeAccounts`, `FakeChannelPluginContext`, `FakeChannelIntake`, `FakeHttp`, `FakeAvatars` and `FakeProcesses`, never host services.

`ChannelsCapability.group(name)` constructs the host account-group coordinator; `ChannelSessions.identity_index(...)` constructs the host metadata-backed identity view. Platform dedupe, credential/authentication, stream formatting and reconnect policy stay in plugins. Use `FakeAccountChannelGroup` and `FakeChannelSessions` for independent tests. Scoped KV supports idempotent `delete`; `read_mapping` validates object-valued records before consumers access them. Telegram tool-call preview events and `EventBinding` are shared SDK values.


## Surface interaction

A background owner declares `surfaces.setInteraction(surfaceId, { roleId, available })`
(or `null` to revoke). The host derives admission from that declaration plus its
existing visibility, readiness and live window identity; private retained state
and plugin KV never participate. Hidden, destroyed or reloading windows cannot
admit speech. An unchanged declaration does not reset an active turn.

Every `SurfaceHandle` receives `voice.gesture("press" | "move" | "release" | "cancel")`,
`voice.onState(listener)` and `onRoleActivity(listener)`. Voice remains host-owned;
an accepted press pins the role before any awaited recording or ASR. Pointer
input is attributed by window identity. A global hotkey uses the active available
owner, otherwise the first available surface in creation order. Another surface
cannot steal a busy turn. Activity contains only role/session identity, phase and
notification intent; `null` resets activity on a target change. Plugins own animation
priority and timing. Reload/crash revokes readiness and stops native drag timers.

`createFakeSurfaceHandle(overrides)` in `/testing` supplies a complete independent
fixture. `pnpm typecheck:plugins` checks every plugin entry and colocated test in a
standalone TypeScript program with declared workspace dependencies and no host
ambient declarations. Boundary tests reject both global bridge calls and host
ambient type references.
