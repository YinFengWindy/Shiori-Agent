# Shiori SDK

`@shiori/sdk` and `shiori-sdk` are the TypeScript and Python distributions of the
same plugin contract. Both are version **3.0.0**, with Runtime API **3.0.0**.
They are built locally and in CI; this repository does not publish them to npm or PyPI.
External plugin manifests declare `runtime_api: ">=3.0.0 <4.0.0"`. The host rejects
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
The first public surface is intentionally small: `PluginRuntimeContext`,
`LifecycleFrame`, `LifecycleModule`, `LifecycleCapability`, `EventsCapability`,
`Dispose`, `EventHandler`, `AfterStepCtx`, `AfterReasoningCtx` and `ResponseMetadata`.
The host owns phase execution, storage, capability authorization and cleanup.
`setup(ctx)` receives its declared capabilities; undeclared access raises
`CapabilityNotGranted`. Runtime injection is checked through a static
`PluginSetupContext` without the legacy context's dynamic attribute fallback.
Further capabilities enter the SDK with their owning migration, not as copies of
host services.

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
in memory; they never open host persistence. `FakeLifecycle` records modules for
explicit execution; it does not simulate the host phase dependency sorter.
HTTP response contracts and tolerant JSON helpers declare httpx/json-repair as
runtime dependencies. pytest-asyncio and test fixtures remain optional.
The base wheel can coexist with pytest without the testing extra: unrelated tests
collect and run normally. Requesting `sdk_context` without the extra reports the
installation requirement. Optional fixtures load only when their dependencies exist.
SDK-only tests never start `AppRuntime`. Real host integration fixtures live in
`shiori_host_testing`; `shiori-plugin-testkit` temporarily forwards those fixtures
for unmigrated plugins and retains their legacy memory fake.

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
uv run python scripts/verify_plugin_tests.py --sdk-only
uv run python scripts/check_sdk_imports.py --base <base-commit>
```

The artifact probes install tarball/wheel non-editably outside the checkout. The
wheel probe first collects/runs an unrelated test with only the base SDK and pytest,
checks the missing-extra diagnostic, then installs the extra and runs all SDK tests.
The plugin probe executes citation, context_pressure, default_memory, shell_safety,
shell_restore, tool_loop_guard, plugin_undo, observe and status_commands with no
host or testkit, plus meme, novelai, story, screen_perception, browser_use and
computer_use. default_memory is installed only for its own target. It verifies installed
origins and that async failures really execute. The original full host CI and
legacy plugin integration job remain enabled.

`scripts/sdk_import_exemptions.json` records individual legacy import edges and
counts, including `TYPE_CHECKING` imports. Remove entries with each migration.
New edges, increased counts, unused entries and host imports from the SDK or
graduated plugins fail the guard. PR CI compares the baseline with its exact base
commit so editing the exemption file cannot silently expand it.


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
