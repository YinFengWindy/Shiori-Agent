import assert from "node:assert/strict";
import { it } from "node:test";
import { mountTestComponent } from "@shiori/plugin-sdk/testing";
import { createPluginRpcTestClient, type PluginRpcTestResponder } from "../shared/testing/pluginRpcTestBridge";
import { MemoryItemDetail } from "./MemoryItemDetail";

const windowGlobals = { miraDesktop: { onEvent: () => () => {} } };

async function renderDetail(respond: PluginRpcTestResponder) {
  const { client, calls } = createPluginRpcTestClient("default_memory", respond);
  const view = await mountTestComponent(<MemoryItemDetail context={{ client, roleId: "mira", refreshKey: 0 }} itemId="m1" />, { windowGlobals });
  return { view, calls, text: view.container.textContent ?? "" };
}

it("shows the full summary and labelled fields of a ready item", async () => {
  const { view, calls, text } = await renderDetail(() => ({ role_id: "mira", status: "ready", item: { id: "m1", summary: "", status: "active", source_ref: "role:mira:1" } }));
  try {
    assert.deepEqual(calls.map((call) => call.params), [{ role_id: "mira", item_id: "m1" }]);
    assert.match(text, /无摘要/);
    assert.match(text, /状态有效/);
    assert.match(text, /来源role:mira:1/);
  } finally {
    await view.cleanup();
  }
});

it("tells a missing item apart from a disabled engine and a failed read", async () => {
  for (const [respond, expected, unexpected] of [
    [() => ({ role_id: "mira", status: "ready", item: null }), /记忆已不存在/, /已停用/],
    [() => ({ role_id: "mira", status: "disabled", item: null }), /语义记忆已停用/, /不存在/],
    [() => { throw new Error("engine offline"); }, /读取失败/, /已停用|不存在/],
  ] satisfies Array<[PluginRpcTestResponder, RegExp, RegExp]>) {
    const { view, text } = await renderDetail(respond);
    try {
      assert.match(text, expected);
      assert.doesNotMatch(text, unexpected);
    } finally {
      await view.cleanup();
    }
  }
});
