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

test("deleting an owned account asks for confirmation and keeps it when the plugin cleanup fails", async () => {
  const environment = await mountTestComponent(null);
  const { RoleAccountsPanel } = await import("./RoleAccountsPanel");
  await environment.cleanup();
  const row = {
    id: "account-1", plugin_id: "test-provider", platform: "test", platform_account_id: "101",
    config_ref: "ref-1", display_name: "Owned", avatar_url: "", role_id: "role-1", plugin_enabled: true,
    runtime_active: true, connection: "online", capabilities: [], known_capabilities: [], error: "",
    response_rules: { private_enabled: true, group_enabled: true, require_mention: true,
      blocked_sender_ids: [], group_rules: [] },
  };
  const deletes: unknown[] = [];
  let rows = [row];
  let failNext = true;
  const view = await mountTestComponent(
    <RoleAccountsPanel roleId="role-1" onOpenPluginSettings={() => undefined} />,
    { windowGlobals: { miraDesktop: {
      onEvent: () => () => undefined,
      invoke: async ({ method, payload }: { method: string; payload: Record<string, unknown> }) => {
        if (method === "accounts.delete") {
          deletes.push(payload);
          if (failNext) {
            failNext = false;
            // The plugin already disconnected before its cleanup failed.
            rows = [{ ...row, connection: "offline" }];
            return { id: "r", type: "response", method, payload: {},
              error: { code: "account_delete_failed", message: "NapCat 文件被占用", details: {} } };
          }
          rows = [];
          return { id: "r", type: "response", method, error: null, payload: { account_id: "account-1" } };
        }
        return { id: "r", type: "response", method, error: null,
          payload: method === "accounts.list" ? { accounts: rows } : { roles: [] } };
      },
    } } },
  );
  try {
    const remove = view.container.querySelector<HTMLButtonElement>('[aria-label="删除 Owned"]');
    assert.ok(remove);
    await act(async () => remove.click());
    const dialog = () => document.querySelector('[role="dialog"]');
    assert.match(dialog()?.textContent ?? "", /test · Owned/);
    assert.deepEqual(deletes, []);
    const confirm = () => Array.from(dialog()?.querySelectorAll("button") ?? [])
      .find((button) => button.textContent === "确认删除");

    await act(async () => confirm()?.click());
    assert.deepEqual(deletes, [{ account_id: "account-1", role_id: "role-1" }]);
    assert.match(dialog()?.textContent ?? "", /NapCat 文件被占用/);
    assert.ok(view.container.querySelector('[aria-label="删除 Owned"]'));
    // The list reloads after a failure too, so the new status is visible.
    assert.match(view.container.textContent ?? "", /离线/);
    assert.doesNotMatch(view.container.textContent ?? "", /在线/);

    await act(async () => confirm()?.click());
    assert.equal(deletes.length, 2);
    assert.equal(view.container.querySelector('[aria-label="删除 Owned"]'), null);
    assert.match(view.container.textContent ?? "", /暂无账号/);
  } finally {
    await view.cleanup();
  }
});
