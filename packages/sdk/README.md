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
checks the missing-extra diagnostic, then installs the extra and runs all SDK tests; the plugin probe executes citation/context_pressure
tests with no host, testkit or default-memory distribution. It verifies installed
origins and that async failures really execute. The original full host CI and
legacy plugin integration job remain enabled.

`scripts/sdk_import_exemptions.json` records individual legacy import edges and
counts, including `TYPE_CHECKING` imports. Remove entries with each migration.
New edges, increased counts, unused entries and host imports from the SDK or
graduated plugins fail the guard. PR CI compares the baseline with its exact base
commit so editing the exemption file cannot silently expand it.
