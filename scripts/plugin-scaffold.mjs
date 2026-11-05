/** Sources for a minimal SDK-only plugin; RPC constants are generated separately. */
export function pluginFiles(id, ui) {
  const distribution = `shiori-plugin-${id.replaceAll("_", "-")}`;
  const files = {
    "manifest.yaml": `api: 4
sdk: ">=5.0.0"
id: ${JSON.stringify(id)}
display_name: ${JSON.stringify(id)}
version: '0.1.0'
distribution: external
entry: backend/plugin.py
inject:
  - rpc
${ui ? "frontend:\n  entry: frontend.ts\n" : ""}`,
    "__init__.py": `"""${id} plugin package."""\n`,
    "backend/__init__.py": `"""${id} backend."""\n`,
    "backend/plugin.py": `"""${id}: a minimal scoped RPC contribution."""

from shiori_sdk.core.services import RPC
from shiori_sdk.rpc import Concurrency
from shiori_sdk.runtime import PluginRuntimeContext


async def ping(payload: dict[str, object]) -> dict[str, object]:
    """Return a small response to verify the plugin connection."""
    return {"status": "ok"}


async def setup(ctx: PluginRuntimeContext) -> None:
    """Register one RPC; the host withdraws it when this scope closes."""
    ctx.require(RPC).register("ping", ping, concurrency=Concurrency.READ_ONLY)
`,
    "pyproject.toml": `[build-system]
requires = ["setuptools>=80", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "${distribution}"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["shiori-sdk>=5.0.0,<6"]

[project.optional-dependencies]
test = ["shiori-sdk[testing]>=5.0.0,<6"]

[tool.setuptools]
include-package-data = false
packages = ["plugins.${id}", "plugins.${id}.backend"]
package-dir = {"plugins.${id}" = "."}

[tool.setuptools.package-data]
"plugins.${id}" = ["manifest.yaml", "TESTING.md"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-W error --import-mode=importlib"
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
required_plugins = ["pytest-asyncio", "shiori-sdk"]
`,
    "tests/contract.json": '{"profile": "rpc"}\n',
    "tests/test_plugin.py": `"""The generated RPC is callable through the SDK test context."""

from pathlib import Path

from shiori_sdk.testing.service_context import FakeServiceContext

from plugins.${id}.backend.plugin import setup


async def test_ping(tmp_path: Path) -> None:
    context = FakeServiceContext(
        "${id}", tmp_path, package_dir=Path(__file__).resolve().parents[1]
    )
    try:
        await setup(context)
        assert await context.fake_rpc.handlers["ping"]({}) == {"status": "ok"}
    finally:
        await context.aclose()
`,
    "TESTING.md": `# ${id} tests

From the Shiori repository root:

\`\`\`sh
uv run pytest plugins/${id}/tests
uv run python -m scripts.verify_plugin_tests --plugins ${id}
uv run python -m scripts.verify_plugin_contracts --plugin-dir plugins/${id} --profile rpc
\`\`\`

The second command builds and tests the plugin wheel outside the repository,
with only SDK/testing and declared dependencies. The third executes the real
host lifecycle. tests/contract.json selects the minimal RPC profile; it rejects
additional services and providers. Add a host lifecycle fixture when this plugin
gains resources, providers or background work.
`,
    "README.md": `# ${id}

API 4 plugin using Shiori SDK 5. The initial RPC is \`ping\`.

After editing backend registrations, run \`pnpm rpc:generate\` and \`pnpm rpc:check\`.
${ui ? "The frontend imports the generated RPC constants and exports an inert UI contribution.\n" : ""}
Build an installable package from the repository root:

\`\`\`sh
node scripts/build-plugin.mjs --plugin plugins/${id} --output artifacts/plugins
\`\`\`

Install the ZIP from plugin settings and approve its trust prompt. Setup does
not execute before approval. Keep credentials and user data outside the package.
See TESTING.md for isolated tests.
`,
  };
  if (ui) Object.assign(files, {
    "package.json": JSON.stringify({ name: `@shiori-plugin/${id}`, version: "0.1.0", private: true, type: "module", peerDependencies: { react: ">=19.2.0 <20.0.0", "react-dom": ">=19.2.0 <20.0.0", "@yinfengwindy/shiori-sdk": ">=5.0.0 <6.0.0" } }, null, 2) + "\n",
    "frontend.ts": '/** Contributions are loaded only when the owning renderer activates them. */\nexport { default as ui } from "./ui/index";\n',
    "ui/index.tsx": `import { useState } from "react";
import { ghostButtonClass, type PluginSettingsSectionComponentProps, type PluginUiModule } from "@yinfengwindy/shiori-sdk";
import { rpcMethods } from "../rpcMethods.generated";

/** Exercise the scoped backend connection from the plugin's settings tab. */
function Settings({ client }: PluginSettingsSectionComponentProps) {
  const [status, setStatus] = useState("");
  const [pending, setPending] = useState(false);
  async function connect() {
    setPending(true);
    try {
      const result = await client.call<{ status: string }>(rpcMethods["ping"]);
      setStatus(result.status);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : String(error));
    } finally {
      setPending(false);
    }
  }
  return <section>
    <button type="button" className={ghostButtonClass} disabled={pending} onClick={() => void connect()}>Check connection</button>
    <output aria-live="polite">{status}</output>
  </section>;
}

const ui: PluginUiModule = {
  pluginId: "${id}",
  settingsSection: { kind: "component", label: "${id}", component: Settings },
};
export default ui;
`,
    "ui/index.test.tsx": `import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { createFakeHostServices, createFakePluginClient, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import ui from "./index";

test("a failed connection is visible and the action can be retried", async () => {
  const contribution = ui.settingsSection;
  assert.ok(contribution?.kind === "component");
  const Settings = contribution.component;
  const client = createFakePluginClient({ call: async () => { throw new Error("Connection lost"); } });
  const { host } = createFakeHostServices();
  const view = await mountTestComponent(<Settings client={client} host={host} subsectionId="${id}" />);
  try {
    const button = view.container.querySelector("button");
    assert.ok(button);
    await act(async () => button.click());
    assert.equal(view.container.querySelector("output")?.textContent, "Connection lost");
    assert.equal(button.disabled, false);
  } finally {
    await view.cleanup();
  }
});
`,
  });
  return files;
}
