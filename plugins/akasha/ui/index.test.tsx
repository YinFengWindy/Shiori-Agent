import assert from "node:assert/strict";
import { it } from "node:test";
import { act } from "react";
import { createPluginRpcClient } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";
import { desktopPluginHostServices } from "../../../apps/desktop/renderer/src/plugins/pluginHostServices";
import { mountTestComponent } from "../../../apps/desktop/renderer/src/shared/testing/domTestHarness";
import { AkashaMemoryDashboard } from "./index";

it("loads role documents through Akasha's namespace", async () => {
  const calls: string[] = [];
  const client = createPluginRpcClient("akasha", async (request) => {
    calls.push(request.method);
    return { id: "1", type: "response", method: request.method, error: null, payload: request.method === "plugins.communication.open"
      ? { generation: "g1" }
      : { role_id: "mira", documents: [
        { name: "SELF.md", status: "ready", content: "# Mira" },
        { name: "MEMORY.md", status: "ready", content: "Second document" },
        { name: "HISTORY.md", status: "error", content: "", error: "denied" },
      ] } };
  });
  const view = await mountTestComponent(<AkashaMemoryDashboard roleId="mira" bridgeReady client={client} host={desktopPluginHostServices} />, { windowGlobals: {
    miraDesktop: { onEvent: () => () => {} },
  } });
  try {
    assert.match(view.container.textContent ?? "", /Mira/);
    assert.match(view.container.textContent ?? "", /Akasha 记忆/);
    assert.deepEqual(calls, ["plugins.communication.open", "plugin.akasha.roles.memory.documents"]);
    const tabs = Array.from(view.container.querySelectorAll<HTMLButtonElement>('[role="tab"]'));
    await act(async () => tabs[1].click());
    assert.match(view.container.textContent ?? "", /Second document/);
    assert.equal(tabs[1].getAttribute("aria-selected"), "true");
    await act(async () => tabs[2].click());
    assert.match(view.container.textContent ?? "", /读取失败：denied/);
    assert.ok(view.container.querySelector('[role="alert"]'));
    await act(async () => view.container.querySelector<HTMLButtonElement>('[aria-label="刷新记忆"]')?.click());
    assert.equal(calls.filter((method) => method === "plugin.akasha.roles.memory.documents").length, 2);
  } finally {
    await view.cleanup();
    await client.dispose();
  }
});
