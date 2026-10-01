import assert from "node:assert/strict";
import { after, before, it } from "node:test";
import { mountTestComponent } from "@shiori/sdk/testing";
import { createPluginRpcTestClient, type PluginRpcTestResponder } from "../shared/testing/pluginRpcTestBridge";
import { memoryReadKey, readMemoryDocuments, readSemanticBatch, readSemanticDetail } from "./memoryReads";
import { initialSemanticQuery } from "./roleSemanticMemory";

// The plugin client subscribes to desktop events when it first connects.
let environment: Awaited<ReturnType<typeof mountTestComponent>>;
before(async () => { environment = await mountTestComponent(null, { windowGlobals: { miraDesktop: { onEvent: () => () => {} } } }); });
after(async () => { await environment.cleanup(); });

function context(respond: PluginRpcTestResponder, roleId = "mira") {
  const { client, calls } = createPluginRpcTestClient("default_memory", respond);
  return { context: { client, roleId, refreshKey: 0 }, calls };
}

it("rejects document and list responses for another role", async () => {
  const { context: mira } = context(() => ({ role_id: "luna", documents: [], status: "ready", items: [], total: 0 }));
  await assert.rejects(readMemoryDocuments(mira), /角色不匹配/);
  await assert.rejects(readSemanticBatch(mira, initialSemanticQuery, 1), /角色不匹配/);
});

it("sends the role, query and batch, and returns a matching response", async () => {
  const list = { role_id: "mira", status: "ready", items: [], total: 0, page: 2, page_size: 20, filters: {} };
  const { context: mira, calls } = context(() => list);
  assert.deepEqual(await readSemanticBatch(mira, { ...initialSemanticQuery, q: "tea" }, 2), list);
  assert.deepEqual(calls, [{ pluginId: "default_memory", name: "roles.memory.semantic.list", params: { role_id: "mira", q: "tea", sort_order: "desc", page: 2, page_size: 20 } }]);
});

it("rejects a detail for another item or role, but accepts a missing item and a disabled engine", async () => {
  await assert.rejects(readSemanticDetail(context(() => ({ role_id: "mira", status: "ready", item: { id: "m2", summary: "" } })).context, "m1"), /记忆条目不匹配/);
  assert.equal((await readSemanticDetail(context(() => ({ role_id: "mira", status: "ready", item: null })).context, "m1")).item, null);
  await assert.rejects(readSemanticDetail(context(() => ({ role_id: "luna", status: "ready", item: { id: "m1", summary: "" } })).context, "m1"), /角色不匹配/);
  assert.equal((await readSemanticDetail(context(() => ({ role_id: "mira", status: "disabled", item: null })).context, "m1")).status, "disabled");
});

it("keys reads by client, role and refresh", () => {
  const { context: base } = context(() => ({}));
  const { context: otherClient } = context(() => ({}));
  assert.equal(memoryReadKey(base, "documents"), memoryReadKey({ ...base }, "documents"));
  for (const changed of [otherClient, { ...base, roleId: "luna" }, { ...base, refreshKey: 1 }]) {
    assert.notEqual(memoryReadKey(changed, "documents"), memoryReadKey(base, "documents"));
  }
});
