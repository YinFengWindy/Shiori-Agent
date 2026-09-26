import assert from "node:assert/strict";
import { it } from "node:test";
import { createPluginRpcClient } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";
import { desktopPluginHostServices } from "../../../apps/desktop/renderer/src/plugins/pluginHostServices";
import { mountTestComponent } from "../../../apps/desktop/renderer/src/shared/testing/domTestHarness";
import { DefaultMemoryDashboard } from "./index";

it("loads role documents through default_memory's namespace", async () => {
  const calls: string[] = [];
  const client = createPluginRpcClient("default_memory", async (request) => {
    calls.push(request.method);
    return { id: "1", type: "response", method: request.method, error: null, payload: request.method === "plugins.communication.open"
      ? { generation: "g1" }
      : { role_id: "mira", documents: [{ name: "SELF.md", status: "ready", content: "# Mira" }] } };
  });
  const view = await mountTestComponent(<DefaultMemoryDashboard roleId="mira" bridgeReady client={client} host={desktopPluginHostServices} />, { windowGlobals: {
    miraDesktop: { onEvent: () => () => {} },
  } });
  try {
    assert.match(view.container.textContent ?? "", /Mira/);
    assert.deepEqual(calls, ["plugins.communication.open", "plugin.default_memory.roles.memory.documents"]);
  } finally {
    await view.cleanup();
    await client.dispose();
  }
});
