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
    const payload = request.method === "plugins.communication.open" ? { generation: "g1" }
      : request.method.endsWith("semantic.list") ? { role_id: "mira", status: "ready", items: [{ id: "role:mira:0", summary: "role:mira:0", memory_type: "turn" }], total: 1 }
      : request.method.endsWith("semantic.detail") ? { role_id: "mira", status: "ready", item: { id: "role:mira:0", summary: "role:mira:0", source_ref: "role:mira:0", extra_json: { role_id: "mira" } } }
      : { role_id: "mira", documents: [
        { name: "SELF.md", status: "ready", content: "# Mira" },
        { name: "MEMORY.md", status: "ready", content: "Second document" },
        { name: "HISTORY.md", status: "error", content: "", error: "denied" },
      ] };
    return { id: "1", type: "response", method: request.method, error: null, payload };
  });
  const view = await mountTestComponent(<AkashaMemoryDashboard roleId="mira" bridgeReady client={client} host={desktopPluginHostServices} />, { windowGlobals: {
    miraDesktop: { onEvent: () => () => {} },
  } });
  try {
    assert.match(view.container.textContent ?? "", /Mira/);
    assert.match(view.container.textContent ?? "", /Akasha 记忆/);
    assert.ok(calls.includes("plugin.akasha.roles.memory.documents"));
    assert.ok(calls.includes("plugin.akasha.roles.memory.semantic.list"));
    assert.equal(view.container.querySelector('[aria-label="记忆状态"]'), null);
    await act(async () => view.container.querySelector<HTMLButtonElement>('[aria-label="查看记忆 role:mira:0"]')?.click());
    assert.ok(calls.includes("plugin.akasha.roles.memory.semantic.detail"));
    const tabs = Array.from(view.container.querySelectorAll<HTMLButtonElement>('[role="tab"]'));
    await act(async () => tabs[1].click());
    assert.match(view.container.textContent ?? "", /Second document/);
    assert.equal(tabs[1].getAttribute("aria-selected"), "true");
    await act(async () => tabs[2].click());
    assert.match(view.container.textContent ?? "", /读取失败：denied/);
    assert.ok(view.container.querySelector('[role="alert"]'));
    await act(async () => view.container.querySelector<HTMLButtonElement>('[aria-label="刷新记忆"]')?.click());
    assert.equal(calls.filter((method) => method === "plugin.akasha.roles.memory.documents").length, 2);
    assert.equal(calls.filter((method) => method === "plugin.akasha.roles.memory.semantic.list").length, 2);
  } finally {
    await view.cleanup();
    await client.dispose();
  }
});
