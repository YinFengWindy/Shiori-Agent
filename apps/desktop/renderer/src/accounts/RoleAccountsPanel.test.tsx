import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import type { BridgeEvent } from "@yinfengwindy/shiori-sdk";
import { changeInputValue, deferred, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { pluginUiRegistry } from "../plugins/pluginUiRegistry";
import { resetPluginEnabledStateForTests, setPluginEnabledSnapshot } from "../plugins/pluginEnabledStateStore";

const avatar = "data:image/png;base64,iVBORw0KGgo=";

const accountRow = {
  id: "account-1", plugin_id: "test-provider", platform: "test", platform_account_id: "101",
  config_ref: "ref-1", display_name: "Owned", avatar_url: "", role_id: "role-1",
  runtime_active: true, connection: "online", capabilities: [], error: "",
  response_rules: { private_enabled: true, group_enabled: true,
    blocked_sender_ids: [] },
};

type Request = { method: string; payload: Record<string, unknown> };

function desktop(
  respond: (request: Request) => Record<string, unknown> | Promise<Record<string, unknown>>,
  onEvent: (listener: (event: BridgeEvent) => void) => () => void = () => () => undefined,
) {
  return { windowGlobals: { miraDesktop: {
    onEvent,
    invoke: async (request: Request) =>
      ({ id: "r", type: "response", method: request.method, error: null, payload: {}, ...await respond(request) }),
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

/** Exercises the real panel, account hook, and client; only bridge replies are controlled. */
async function mountRulesPanel({ loseSaveResponse = false }: { loseSaveResponse?: boolean } = {}) {
  const RoleAccountsPanel = await loadPanel();
  setPluginEnabledSnapshot([{ id: "test-provider", enabled: true, state: "ACTIVE" }]);
  registerPlatform("test-provider", "Test");
  const writes: Request[] = [];
  const reads: Array<ReturnType<typeof deferred<Record<string, unknown>>>> = [];
  const listeners = new Set<(event: BridgeEvent) => void>();
  let hostRules: unknown = { ...accountRow.response_rules, allow_full_tools: true };
  let firstRead = true;
  const row = () => ({ ...accountRow, capabilities: ["full_tools"], response_rules: hostRules });
  const view = await mountTestComponent(<RoleAccountsPanel roleId="role-1" />, desktop((request) => {
    if (request.method === "accounts.rules.set") {
      writes.push(request);
      hostRules = request.payload.response_rules;
      if (loseSaveResponse) return { error: { code: "bridge_timeout", message: "请求超时，请稍后重试", details: { outcome: "unknown" } } };
      return { payload: { account: row() } };
    }
    assert.equal(request.method, "accounts.list");
    if (firstRead) {
      firstRead = false;
      return { payload: { accounts: [row()] } };
    }
    const read = deferred<Record<string, unknown>>();
    reads.push(read);
    return read.promise;
  }, (listener) => { listeners.add(listener); return () => { listeners.delete(listener); }; }));
  await act(async () => view.container.querySelector("button")?.click());
  const toggle = document.querySelector<HTMLButtonElement>('[role="dialog"] [role="switch"][aria-label="允许完整工具权限"]');
  const blocked = document.querySelector<HTMLTextAreaElement>('[role="dialog"] textarea');
  assert.ok(toggle); assert.ok(blocked);
  return { writes, reads, toggle, blocked,
    retry: () => {
      const button = Array.from(dialog()?.querySelectorAll("button") ?? []).find((item) => item.textContent === "重试");
      assert.ok(button); return button;
    },
    settleRead: (index: number, fail = false) => act(async () => {
      assert.ok(reads[index]);
      reads[index].resolve(fail
        ? { error: { code: "account_read_failed", message: "账号读取失败", details: {} } }
        : { payload: { accounts: [row()] } });
    }),
    emit: () => act(async () => {
      for (const listener of listeners) listener({ id: "e", type: "event", method: "accounts.updated", payload: { account_id: accountRow.id } });
    }),
    cleanup: async () => {
      await view.cleanup();
      pluginUiRegistry.unregisterPlugin("test-provider");
      resetPluginEnabledStateForTests();
    },
  };
}

test("rules stay locked after a successful revocation until a failed account refresh is retried successfully", async () => {
  const view = await mountRulesPanel();
  try {
    assert.equal(view.toggle.getAttribute("aria-checked"), "true");
    await changeInputValue(view.blocked, "draft-peer");
    await act(async () => view.toggle.click());
    assert.equal(view.writes.length, 1);
    assert.equal(view.blocked.disabled, true);
    await view.settleRead(0, true);
    assert.match(dialog()?.textContent ?? "", /账号读取失败/);
    assert.equal(view.toggle.disabled, true);
    assert.equal(view.blocked.disabled, true);
    assert.equal(view.blocked.value, "draft-peer");
    await act(async () => {
      view.toggle.click();
      view.blocked.dispatchEvent(new FocusEvent("focusout", { bubbles: true }));
    });
    assert.equal(view.writes.length, 1, "stale rules cannot be written while the latest read failed");
    await act(async () => view.retry().click());
    assert.equal(view.retry().disabled, true);
    assert.equal(view.blocked.disabled, true);
    assert.match(dialog()?.textContent ?? "", /账号读取失败/);
    await view.settleRead(1, true);
    assert.equal(view.blocked.disabled, true);
    await act(async () => view.retry().click());
    assert.equal(view.blocked.disabled, true);
    await view.settleRead(2);
    assert.equal(view.toggle.getAttribute("aria-checked"), "false");
    assert.equal(view.blocked.disabled, false);
    assert.equal(view.blocked.value, "draft-peer");
    assert.doesNotMatch(dialog()?.textContent ?? "", /账号读取失败/);
    await act(async () => view.blocked.dispatchEvent(new FocusEvent("focusout", { bubbles: true })));
    assert.deepEqual(view.writes[1].payload.response_rules, {
      private_enabled: true, group_enabled: true, blocked_sender_ids: ["draft-peer"],
    });
    await view.settleRead(3);
    assert.equal(view.toggle.getAttribute("aria-checked"), "false");
  } finally { await view.cleanup(); }
});

test("a superseded post-save refresh cannot unlock rules while the newer host read is pending", async () => {
  const view = await mountRulesPanel();
  try {
    await changeInputValue(view.blocked, "draft-peer");
    await act(async () => view.toggle.click());
    await view.emit();
    assert.equal(view.reads.length, 2);
    await view.settleRead(0);
    assert.equal(view.toggle.disabled, true);
    assert.equal(view.blocked.disabled, true);
    await act(async () => {
      view.toggle.click();
      view.blocked.dispatchEvent(new FocusEvent("focusout", { bubbles: true }));
    });
    assert.equal(view.writes.length, 1);
    await view.settleRead(1);
    assert.equal(view.toggle.getAttribute("aria-checked"), "false");
    assert.equal(view.blocked.disabled, false);
    assert.equal(view.blocked.value, "draft-peer");
    await act(async () => view.blocked.dispatchEvent(new FocusEvent("focusout", { bubbles: true })));
    assert.deepEqual(view.writes[1].payload.response_rules, {
      private_enabled: true, group_enabled: true, blocked_sender_ids: ["draft-peer"],
    });
    await view.settleRead(2);
  } finally { await view.cleanup(); }
});

test("an unknown rule-save outcome also requires a confirmed host snapshot before further edits", async () => {
  const view = await mountRulesPanel({ loseSaveResponse: true });
  try {
    await changeInputValue(view.blocked, "draft-peer");
    await act(async () => view.toggle.click());
    assert.equal(view.reads.length, 1, "a failed bridge reply does not confirm that the rules were unchanged");
    assert.equal(view.blocked.disabled, true);
    await view.settleRead(0, true);
    assert.match(dialog()?.textContent ?? "", /请求超时/);
    assert.equal(view.blocked.disabled, true);
    await act(async () => view.retry().click());
    await view.settleRead(1);
    assert.equal(view.toggle.getAttribute("aria-checked"), "false");
    assert.equal(view.blocked.disabled, false);
    assert.equal(view.blocked.value, "draft-peer");
    await act(async () => view.blocked.dispatchEvent(new FocusEvent("focusout", { bubbles: true })));
    assert.deepEqual(view.writes[1].payload.response_rules, {
      private_enabled: true, group_enabled: true, blocked_sender_ids: ["draft-peer"],
    });
    await view.settleRead(2);
    assert.equal(view.toggle.getAttribute("aria-checked"), "false");
  } finally { await view.cleanup(); }
});

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

for (const connection of ["offline", "error", "connecting"]) {
  test(`a saved account can edit its full tool grant while ${connection}`, async () => {
    const RoleAccountsPanel = await loadPanel();
    setPluginEnabledSnapshot([{ id: "test-provider", enabled: true, state: "ACTIVE" }]);
    registerPlatform("test-provider", "Test");
    const changes: Request[] = [];
    let enabled = false;
    const row = () => ({ ...accountRow, connection, capabilities: ["full_tools"],
      response_rules: { ...accountRow.response_rules, allow_full_tools: enabled } });
    const view = await mountTestComponent(<RoleAccountsPanel roleId="role-1" />,
      desktop((request) => {
        if (request.method === "accounts.rules.set") {
          changes.push(request);
          const rules = request.payload.response_rules;
          assert.ok(rules && typeof rules === "object");
          enabled = Reflect.get(rules, "allow_full_tools") === true;
          return { payload: { account: row() } };
        }
        return { payload: request.method === "accounts.list" ? { accounts: [row()] } : {} };
      }));
    try {
      await act(async () => view.container.querySelector("button")?.click());
      const toggle = document.querySelector<HTMLButtonElement>('[role="dialog"] [role="switch"][aria-label="允许完整工具权限"]');
      assert.ok(toggle);
      assert.equal(toggle.getAttribute("aria-checked"), "false");
      await act(async () => toggle.click());
      assert.equal(toggle.getAttribute("aria-checked"), "true");
      assert.deepEqual(changes, [{ method: "accounts.rules.set", payload: {
        account_id: "account-1", response_rules: { private_enabled: true,
          group_enabled: true, blocked_sender_ids: [], allow_full_tools: true },
      } }]);
    } finally {
      await view.cleanup();
      pluginUiRegistry.unregisterPlugin("test-provider");
      resetPluginEnabledStateForTests();
    }
  });
}

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
