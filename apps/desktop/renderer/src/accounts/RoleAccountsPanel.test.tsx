import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { pluginUiRegistry } from "../plugins/pluginUiRegistry";

test("owned account connection action opens the shared platform controls", async () => {
  const environment = await mountTestComponent(null);
  const { RoleAccountsPanel } = await import("./RoleAccountsPanel");
  await environment.cleanup();
  pluginUiRegistry.registerAccountDetail({
    slot: "account.detail", pluginId: "test-provider",
    Component: ({ account }) => <button type="button">平台操作 {account?.id}</button>,
  });
  const view = await mountTestComponent(
    <RoleAccountsPanel roleId="role-1" onOpenPluginSettings={() => undefined} />,
    { windowGlobals: { miraDesktop: {
      onEvent: () => () => undefined,
      invoke: async ({ method }: { method: string }) => ({ id: "response", type: "response", method,
        error: null, payload: method === "accounts.list" ? { accounts: [{
          id: "account-1", plugin_id: "test-provider", platform: "test", platform_account_id: "101",
          display_name: "Owned", avatar_url: "", role_id: "role-1", plugin_enabled: true,
          runtime_active: true, connection: "online", capabilities: [], known_capabilities: [], error: "",
          response_rules: { private_enabled: true, group_enabled: true, require_mention: true,
            blocked_sender_ids: [], group_rules: [] },
        }] } : { roles: [] } }),
    } } },
  );
  try {
    const action = view.container.querySelector<HTMLButtonElement>('[aria-label="管理 Owned 的连接"]');
    assert.ok(action);
    assert.equal(action.textContent, "管理连接");
    await act(async () => action.click());
    assert.match(document.querySelector('[role="dialog"]')?.textContent ?? "", /平台操作 account-1/);
  } finally {
    await view.cleanup();
    pluginUiRegistry.unregisterPlugin("test-provider");
  }
});
