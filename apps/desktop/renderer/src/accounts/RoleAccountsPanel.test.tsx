import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { pluginUiRegistry } from "../plugins/pluginUiRegistry";
import { resetPluginEnabledStateForTests, setPluginEnabledSnapshot } from "../plugins/pluginEnabledStateStore";

const accountRow = {
  id: "account-1", plugin_id: "test-provider", platform: "test", platform_account_id: "101",
  config_ref: "ref-1", display_name: "Owned", avatar_url: "", role_id: "role-1",
  runtime_active: true, connection: "online", capabilities: [], error: "",
  response_rules: { private_enabled: true, group_enabled: true, require_mention: true,
    blocked_sender_ids: [], group_rules: [] },
};

type Request = { method: string; payload: Record<string, unknown> };

function desktop(respond: (request: Request) => Record<string, unknown>) {
  return { windowGlobals: { miraDesktop: {
    onEvent: () => () => undefined,
    invoke: async (request: Request) =>
      ({ id: "r", type: "response", method: request.method, error: null, payload: {}, ...respond(request) }),
  } } };
}

function registerPlatform(pluginId: string, label: string) {
  pluginUiRegistry.registerAccountDetail({
    slot: "account.detail", pluginId, label,
    Icon: ({ className }) => <svg className={className} data-testid={`${pluginId}-icon`} />,
    Component: ({ account, roleId }) => <button type="button">平台操作 {account?.id ?? "new"} {roleId}</button>,
  });
}

test("owned account detail opens the platform controls for this role, without owner or claim controls", async () => {
  const environment = await mountTestComponent(null);
  const { RoleAccountsPanel } = await import("./RoleAccountsPanel");
  await environment.cleanup();
  setPluginEnabledSnapshot([{ id: "test-provider", enabled: true, state: "ACTIVE" }]);
  registerPlatform("test-provider", "Test");
  const view = await mountTestComponent(
    <RoleAccountsPanel roleId="role-1" />,
    desktop(({ method }) => ({ payload: method === "accounts.list" ? { accounts: [accountRow] } : {} })),
  );
  try {
    // Platform, nickname, platform account and live status are listed.
    assert.match(view.container.textContent ?? "", /Owned · 101 · 在线/);
    assert.ok(view.container.querySelector('[data-testid="test-provider-icon"]'));
    assert.match(view.container.textContent ?? "", /101/);
    assert.match(view.container.textContent ?? "", /在线/);
    const action = Array.from(view.container.querySelectorAll<HTMLButtonElement>("button"))
      .find((button) => button.textContent === "查看");
    assert.ok(action);
    await act(async () => action.click());
    const dialog = document.querySelector('[role="dialog"]')?.textContent ?? "";
    assert.match(dialog, /平台操作 account-1 role-1/);
    assert.doesNotMatch(dialog, /所属角色|旧渠道归属待确认/);
    assert.doesNotMatch(view.container.textContent ?? "", /认领/);
  } finally {
    await view.cleanup();
    pluginUiRegistry.unregisterPlugin("test-provider");
    resetPluginEnabledStateForTests();
  }
});

test("enabled channels stay visible as rows with add or view actions; disabled channels stay hidden", async () => {
  const environment = await mountTestComponent(null);
  const { RoleAccountsPanel } = await import("./RoleAccountsPanel");
  await environment.cleanup();
  resetPluginEnabledStateForTests();
  setPluginEnabledSnapshot([
    { id: "test-provider", enabled: true, state: "ACTIVE" },
    { id: "other-provider", enabled: true, state: "ACTIVE" },
    { id: "off-provider", enabled: false, state: "DISABLED" },
  ]);
  registerPlatform("test-provider", "Test");
  registerPlatform("other-provider", "Other");
  registerPlatform("off-provider", "Off");
  const view = await mountTestComponent(
    <RoleAccountsPanel roleId="role-1" />,
    desktop(({ method }) => ({ payload: method === "accounts.list" ? { accounts: [accountRow] } : {} })),
  );
  try {
    const buttons = Array.from(view.container.querySelectorAll<HTMLButtonElement>("button"));
    assert.equal(buttons.some((button) => button.textContent === "添加账号"), false);
    assert.match(view.container.textContent ?? "", /Test[\s\S]*Owned · 101 · 在线[\s\S]*Other[\s\S]*未添加/);
    assert.doesNotMatch(view.container.textContent ?? "", /Off/);
    assert.ok(view.container.querySelector('[data-testid="other-provider-icon"]'));
    const add = buttons.find((button) => button.textContent?.includes("添加"));
    assert.ok(add);
    await act(async () => add.click());
    // The new account's form is opened for this role.
    assert.match(document.querySelector('[role="dialog"]')?.textContent ?? "", /添加 Other 账号[\s\S]*平台操作 new role-1/);
  } finally {
    await view.cleanup();
    for (const pluginId of ["test-provider", "other-provider", "off-provider"]) pluginUiRegistry.unregisterPlugin(pluginId);
    resetPluginEnabledStateForTests();
  }
});

test("deleting an owned account asks for confirmation and keeps it when the plugin cleanup fails", async () => {
  const environment = await mountTestComponent(null);
  const { RoleAccountsPanel } = await import("./RoleAccountsPanel");
  await environment.cleanup();
  setPluginEnabledSnapshot([{ id: "test-provider", enabled: true, state: "ACTIVE" }]);
  registerPlatform("test-provider", "Test");
  const deletes: unknown[] = [];
  let rows = [accountRow];
  let failNext = true;
  const view = await mountTestComponent(
    <RoleAccountsPanel roleId="role-1" />,
    desktop(({ method, payload }) => {
      if (method === "accounts.delete") {
        deletes.push(payload);
        if (failNext) {
          failNext = false;
          // The plugin already disconnected before its cleanup failed.
          rows = [{ ...accountRow, connection: "offline" }];
          return { error: { code: "account_delete_failed", message: "NapCat 文件被占用", details: {} } };
        }
        rows = [];
        return { payload: { account_id: "account-1" } };
      }
      return { payload: method === "accounts.list" ? { accounts: rows } : {} };
    }),
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
    assert.match(view.container.textContent ?? "", /未添加/);
  } finally {
    await view.cleanup();
    pluginUiRegistry.unregisterPlugin("test-provider");
    resetPluginEnabledStateForTests();
  }
});
