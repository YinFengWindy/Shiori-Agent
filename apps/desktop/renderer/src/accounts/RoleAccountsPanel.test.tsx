import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { mountTestComponent } from "@shiori/plugin-sdk/testing";
import { pluginUiRegistry } from "../plugins/pluginUiRegistry";
import { resetPluginEnabledStateForTests, setPluginEnabledSnapshot } from "../plugins/pluginEnabledStateStore";

const avatar = "data:image/png;base64,iVBORw0KGgo=";

const accountRow = {
  id: "account-1", plugin_id: "test-provider", platform: "test", platform_account_id: "101",
  config_ref: "ref-1", display_name: "Owned", avatar_url: "", role_id: "role-1",
  runtime_active: true, connection: "online", capabilities: [], error: "",
  response_rules: { private_enabled: true, group_enabled: true, require_mention: true,
    blocked_sender_ids: [] },
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
    Component: ({ account, roleId }) => <p>平台操作 {account?.id ?? "new"} {roleId}</p>,
  });
}

async function loadPanel() {
  const environment = await mountTestComponent(null);
  const { RoleAccountsPanel } = await import("./RoleAccountsPanel");
  await environment.cleanup();
  return RoleAccountsPanel;
}

const dialog = () => document.querySelector('[role="dialog"]');

test("each channel is one whole-row button that opens its detail; the account's avatar carries the channel badge", async () => {
  const RoleAccountsPanel = await loadPanel();
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
    desktop(({ method }) => ({ payload: method === "accounts.list" ? { accounts: [{ ...accountRow, avatar_url: avatar }] } : {} })),
  );
  try {
    const rows = Array.from(view.container.querySelectorAll<HTMLButtonElement>("button"));
    // One button per enabled channel and nothing else: no 查看 / 添加 / 删除 buttons.
    assert.deepEqual(rows.map((row) => row.getAttribute("aria-label")), ["Owned，在线，Test · 101", "添加 Other 账号"]);
    assert.doesNotMatch(view.container.textContent ?? "", /查看|删除|Off/);
    // Nickname with the status dot beside it, then channel · platform ID.
    const [owned, other] = rows;
    assert.match(owned.textContent ?? "", /^Owned\s*Test · 101$/);
    assert.equal(owned.querySelector('[role="img"]')?.getAttribute("aria-label"), "在线");
    assert.equal(owned.querySelector("img")?.getAttribute("src"), avatar);
    assert.ok(owned.querySelector('[data-avatar="account"] [data-testid="test-provider-icon"]'));
    // Not added yet: the channel's own tile, its label, and 未添加.
    assert.match(other.textContent ?? "", /^Other\s*未添加$/);
    assert.equal(other.querySelector("img"), null);
    assert.ok(other.querySelector('[data-avatar="channel"] [data-testid="other-provider-icon"]'));

    await act(async () => other.click());
    assert.match(dialog()?.textContent ?? "", /添加 Other 账号[\s\S]*平台操作 new role-1/);
  } finally {
    await view.cleanup();
    for (const pluginId of ["test-provider", "other-provider", "off-provider"]) pluginUiRegistry.unregisterPlugin(pluginId);
    resetPluginEnabledStateForTests();
  }
});

test("an account without a picture shows its channel tile; its detail puts platform controls, rules, then the danger zone", async () => {
  const RoleAccountsPanel = await loadPanel();
  setPluginEnabledSnapshot([{ id: "test-provider", enabled: true, state: "ACTIVE" }]);
  registerPlatform("test-provider", "Test");
  const view = await mountTestComponent(
    <RoleAccountsPanel roleId="role-1" />,
    desktop(({ method }) => ({ payload: method === "accounts.list" ? { accounts: [accountRow] } : {} })),
  );
  try {
    const row = view.container.querySelector<HTMLButtonElement>("button");
    assert.ok(row?.querySelector('[data-avatar="channel"]'));
    assert.equal(row?.querySelector("img"), null);
    await act(async () => row?.click());
    assert.equal(document.querySelector('[role="dialog"] h2')?.textContent, "Owned");
    assert.match(dialog()?.textContent ?? "", /Test · 101[\s\S]*平台操作 account-1 role-1[\s\S]*响应规则[\s\S]*删除账号/);
    assert.ok(document.querySelector('[role="dialog"] [aria-label="关闭账号详情"]'));
    assert.doesNotMatch(dialog()?.textContent ?? "", /所属角色|认领|保存规则/);
  } finally {
    await view.cleanup();
    pluginUiRegistry.unregisterPlugin("test-provider");
    resetPluginEnabledStateForTests();
  }
});

test("response rules are left out while the account is not online", async () => {
  const RoleAccountsPanel = await loadPanel();
  setPluginEnabledSnapshot([{ id: "test-provider", enabled: true, state: "ACTIVE" }]);
  registerPlatform("test-provider", "Test");
  const view = await mountTestComponent(
    <RoleAccountsPanel roleId="role-1" />,
    desktop(({ method }) => ({ payload: method === "accounts.list" ? { accounts: [{ ...accountRow, connection: "login_required" }] } : {} })),
  );
  try {
    await act(async () => view.container.querySelector("button")?.click());
    assert.doesNotMatch(dialog()?.textContent ?? "", /响应规则|私聊启用/);
    assert.match(dialog()?.textContent ?? "", /删除账号/);
  } finally {
    await view.cleanup();
    pluginUiRegistry.unregisterPlugin("test-provider");
    resetPluginEnabledStateForTests();
  }
});

test("删除账号 in the detail asks for confirmation, keeps the account when cleanup fails, and closes the detail once deleted", async () => {
  const RoleAccountsPanel = await loadPanel();
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
    await act(async () => view.container.querySelector("button")?.click());
    const buttonIn = (root: ParentNode | null | undefined, label: string) => Array.from(root?.querySelectorAll("button") ?? [])
      .find((button) => button.textContent === label);
    await act(async () => buttonIn(dialog(), "删除账号")?.click());
    const confirmation = () => Array.from(document.querySelectorAll('[role="dialog"]'))
      .find((item) => item.textContent?.includes("确认删除"));
    assert.match(confirmation()?.textContent ?? "", /test · Owned/);
    assert.deepEqual(deletes, []);

    await act(async () => buttonIn(confirmation(), "确认删除")?.click());
    assert.deepEqual(deletes, [{ account_id: "account-1", role_id: "role-1" }]);
    assert.match(confirmation()?.textContent ?? "", /NapCat 文件被占用/);
    // The list reloads after a failure too, so the new status is visible.
    assert.equal(view.container.querySelector('[role="img"]')?.getAttribute("aria-label"), "离线");

    await act(async () => buttonIn(confirmation(), "确认删除")?.click());
    assert.equal(deletes.length, 2);
    assert.equal(document.querySelector('[role="dialog"]'), null);
    assert.match(view.container.textContent ?? "", /未添加/);
  } finally {
    await view.cleanup();
    pluginUiRegistry.unregisterPlugin("test-provider");
    resetPluginEnabledStateForTests();
  }
});
