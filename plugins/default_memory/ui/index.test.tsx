import assert from "node:assert/strict";
import { before, it } from "node:test";
import { act } from "react";
import { createPluginRpcClient } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";
import { mountTestComponent } from "../../../apps/desktop/renderer/src/shared/testing/domTestHarness";
import { chooseSelectOption } from "../../../apps/desktop/renderer/src/shared/testing/selectTestActions";

// Base UI binds DOM globals at import time, so the Dashboard and host UI load inside a test window.
let DefaultMemoryDashboard: typeof import("./index").DefaultMemoryDashboard;
let desktopPluginHostServices: typeof import("../../../apps/desktop/renderer/src/plugins/pluginHostServices").desktopPluginHostServices;
before(async () => {
  const environment = await mountTestComponent(null);
  ({ DefaultMemoryDashboard } = await import("./index"));
  ({ desktopPluginHostServices } = await import("../../../apps/desktop/renderer/src/plugins/pluginHostServices"));
  await environment.cleanup();
});

it("loads role documents through default_memory's namespace", async () => {
  const calls: string[] = [];
  const listParams: unknown[] = [];
  const client = createPluginRpcClient("default_memory", async (request) => {
    calls.push(request.method);
    if (request.method.endsWith("semantic.list")) listParams.push(Object.fromEntries(Object.entries(request.payload).filter(([key]) => key !== "__plugin_context")));
    const payload = request.method === "plugins.communication.open" ? { generation: "g1" }
      : request.method.endsWith("semantic.list") ? { role_id: "mira", status: "ready", items: [{ id: "m1", summary: "Mira likes tea", memory_type: "preference", status: "active" }], total: 1, page: 1, page_size: 20, filters: { memory_type: ["preference"], memory_domain: ["taste"], status: ["active", "superseded", "all"] } }
      : request.method.endsWith("semantic.detail") ? { role_id: "mira", status: "ready", item: { id: "m1", summary: "Mira likes tea", source_ref: "role:mira:1", extra_json: { role_id: "mira" } } }
      : { role_id: "mira", documents: [
        { name: "SELF.md", status: "ready", content: "# Mira" },
        { name: "MEMORY.md", status: "ready", content: "Second document" },
        { name: "HISTORY.md", status: "error", content: "", error: "denied" },
      ] };
    return { id: "1", type: "response", method: request.method, error: null, payload };
  });
  const view = await mountTestComponent(<DefaultMemoryDashboard roleId="mira" bridgeReady client={client} host={desktopPluginHostServices} />, { windowGlobals: {
    miraDesktop: { onEvent: () => () => {} },
  } });
  try {
    assert.match(view.container.textContent ?? "", /Mira/);
    assert.match(view.container.textContent ?? "", /默认记忆/);
    assert.ok(calls.includes("plugin.default_memory.roles.memory.documents"));
    assert.ok(calls.includes("plugin.default_memory.roles.memory.semantic.list"));
    assert.match(view.container.textContent ?? "", /Mira likes tea/);
    assert.deepEqual(Array.from(view.container.querySelectorAll('[role="combobox"]')).map((element) => element.getAttribute("aria-label")), ["记忆类型", "记忆领域", "记忆状态", "时间排序"]);
    await chooseSelectOption("记忆类型", "preference");
    assert.deepEqual(listParams.at(-1), { role_id: "mira", q: "", sort_order: "desc", page: 1, page_size: 20, memory_type: "preference" });
    await act(async () => view.container.querySelector<HTMLButtonElement>('[aria-label="查看记忆 m1"]')?.click());
    assert.ok(calls.includes("plugin.default_memory.roles.memory.semantic.detail"));
    assert.match(view.container.textContent ?? "", /role:mira:1/);
    const tabs = Array.from(view.container.querySelectorAll<HTMLButtonElement>('[role="tab"]'));
    await act(async () => tabs[1].click());
    assert.match(view.container.textContent ?? "", /Second document/);
    assert.equal(tabs[1].getAttribute("aria-selected"), "true");
    await act(async () => tabs[2].click());
    assert.match(view.container.textContent ?? "", /读取失败：denied/);
    assert.ok(view.container.querySelector('[role="alert"]'));
    await act(async () => view.container.querySelector<HTMLButtonElement>('[aria-label="刷新记忆"]')?.click());
    assert.equal(calls.filter((method) => method === "plugin.default_memory.roles.memory.documents").length, 2);
    assert.equal(calls.filter((method) => method === "plugin.default_memory.roles.memory.semantic.list").length, 3);
  } finally {
    await view.cleanup();
    await client.dispose();
  }
});

it("keeps Markdown readable after a semantic request fails", async () => {
  const client = createPluginRpcClient("default_memory", async (request) => ({
    id: "1", type: "response", method: request.method,
    error: request.method.endsWith("semantic.list") ? { code: "read_failed", message: "semantic unavailable" } : null,
    payload: request.method === "plugins.communication.open" ? { generation: "g1" }
      : { role_id: "mira", documents: [{ name: "SELF.md", status: "ready", content: "# Mira" }] },
  }));
  const view = await mountTestComponent(<DefaultMemoryDashboard roleId="mira" bridgeReady client={client} host={desktopPluginHostServices} />, { windowGlobals: {
    miraDesktop: { onEvent: () => () => {} },
  } });
  try {
    assert.match(view.container.textContent ?? "", /semantic unavailable/);
    assert.match(view.container.textContent ?? "", /Mira/);
  } finally {
    await view.cleanup();
    await client.dispose();
  }
});
