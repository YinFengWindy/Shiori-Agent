import assert from "node:assert/strict";
import { test } from "node:test";
import { act, useState } from "react";
import { changeInputValue, mountTestComponent } from "../shared/testing/domTestHarness";
import { pluginUiRegistry, type PluginAccountDetailProps } from "../plugins/pluginUiRegistry";

test("new account stays in one detail through separate save, connect, and failure", async () => {
  const environment = await mountTestComponent(null);
  const { PluginAccountsSection } = await import("./PluginAccountsSection");
  await environment.cleanup();
  let savedCredential: string | null = null;
  let liveCredential = "old-secret";
  function FakeAccountControls({ account, onChanged }: PluginAccountDetailProps) {
    const [draft, setDraft] = useState("old-secret");
    const [error, setError] = useState("");
    return <div>
      {account ? <span>已保存账号: {account.id}</span> : null}
      <input aria-label="测试凭据" value={draft} onChange={(event) => setDraft(event.target.value)} />
      <button type="button" onClick={() => { savedCredential = draft; onChanged("account-1"); }}>保存</button>
      <button type="button" disabled={!account} onClick={() => {
        if (savedCredential === "reject") { setError("连接失败"); return; }
        liveCredential = savedCredential ?? liveCredential;
      }}>连接</button>
      {error ? <span role="alert">{error}</span> : null}
    </div>;
  }
  pluginUiRegistry.registerAccountDetail({ slot: "account.detail", pluginId: "test-provider", Component: FakeAccountControls });
  const wireAccount = {
    id: "account-1", plugin_id: "test-provider", platform: "test", platform_account_id: "101",
    display_name: "Live account", avatar_url: "", role_id: null,
    plugin_enabled: true, runtime_active: true, connection: "offline",
    capabilities: [], known_capabilities: [], error: "",
    response_rules: { private_enabled: true, group_enabled: true, require_mention: true,
      blocked_sender_ids: [], group_rules: [] },
  };
  const view = await mountTestComponent(<PluginAccountsSection pluginId="test-provider" />, {
    windowGlobals: { miraDesktop: {
      invoke: async ({ method }: { method: string }) => ({ id: "response", type: "response", method,
        error: null, payload: method === "accounts.list"
          ? { accounts: savedCredential === null ? [] : [wireAccount] }
          : { roles: [] } }),
      onEvent: () => () => undefined,
    } },
  });
  try {
    const button = (label: string) => Array.from(document.querySelectorAll<HTMLButtonElement>("button"))
      .find((item) => item.textContent === label);
    await act(async () => button("添加账号")?.click());
    const input = document.querySelector<HTMLInputElement>('[aria-label="测试凭据"]');
    assert.ok(input);
    await changeInputValue(input, "new-secret");
    assert.equal(liveCredential, "old-secret");
    assert.equal(savedCredential, null);
    await act(async () => button("保存")?.click());
    assert.equal(savedCredential, "new-secret");
    assert.equal(liveCredential, "old-secret");
    assert.match(document.querySelector('[role="dialog"]')?.textContent ?? "", /已保存账号: account-1/);
    await act(async () => button("连接")?.click());
    assert.equal(liveCredential, "new-secret");
    await changeInputValue(input, "reject");
    await act(async () => button("保存")?.click());
    await act(async () => button("连接")?.click());
    assert.equal(liveCredential, "new-secret");
    assert.match(document.querySelector('[role="dialog"]')?.textContent ?? "", /连接失败/);
  } finally {
    await view.cleanup();
    pluginUiRegistry.unregisterPlugin("test-provider");
  }
});
