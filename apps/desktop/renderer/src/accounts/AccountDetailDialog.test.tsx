import assert from "node:assert/strict";
import { test } from "node:test";
import { act, useState } from "react";
import { changeInputValue, mountTestComponent } from "../shared/testing/domTestHarness";
import { pluginUiRegistry } from "../plugins/pluginUiRegistry";
import type { AccountSnapshot } from "./accountClient";

const account: AccountSnapshot = {
  id: "account-1", pluginId: "test-provider", platform: "test", platformAccountId: "101",
  displayName: "Live account", avatarUrl: "", roleId: null, pluginEnabled: true,
  runtimeActive: true, connection: "online", capabilities: [], error: "",
  responseRules: { privateEnabled: true, groupEnabled: true, requireMention: true, blockedSenderIds: [], groupRules: [] },
};

test("plugin account draft leaves live connection untouched until explicit save and connect", async () => {
  const environment = await mountTestComponent(null);
  const { AccountDetailDialog } = await import("./AccountDetailDialog");
  await environment.cleanup();
  let liveCredential = "old-secret";
  let changed = 0;
  function FakeAccountControls() {
    const [draft, setDraft] = useState(liveCredential);
    const [error, setError] = useState("");
    return <div>
      <input aria-label="测试凭据" value={draft} onChange={(event) => setDraft(event.target.value)} />
      <button type="button" onClick={() => {
        if (draft === "reject") { setError("连接失败"); return; }
        liveCredential = draft;
        changed += 1;
      }}>保存并连接</button>
      {error ? <span role="alert">{error}</span> : null}
    </div>;
  }
  pluginUiRegistry.registerAccountDetail({ slot: "account.detail", pluginId: "test-provider", Component: FakeAccountControls });
  const view = await mountTestComponent(
    <AccountDetailDialog account={account} pluginId="test-provider" onClose={() => undefined} onChanged={() => undefined} />,
    { windowGlobals: { miraDesktop: {
      invoke: async ({ method }: { method: string }) => ({ id: "response", type: "response", method, error: null, payload: { roles: [] } }),
      onEvent: () => () => undefined,
    } } },
  );
  try {
    const input = document.querySelector<HTMLInputElement>('[aria-label="测试凭据"]');
    assert.ok(input);
    await changeInputValue(input, "new-secret");
    assert.equal(liveCredential, "old-secret");
    assert.equal(changed, 0);
    const connect = Array.from(document.querySelectorAll<HTMLButtonElement>("button")).find((button) => button.textContent === "保存并连接");
    assert.ok(connect);
    await act(async () => connect.click());
    assert.equal(liveCredential, "new-secret");
    assert.equal(changed, 1);
    await changeInputValue(input, "reject");
    await act(async () => connect.click());
    assert.equal(liveCredential, "new-secret");
    assert.match(document.body.textContent ?? "", /连接失败/);
  } finally {
    await view.cleanup();
    pluginUiRegistry.unregisterPlugin("test-provider");
  }
});
