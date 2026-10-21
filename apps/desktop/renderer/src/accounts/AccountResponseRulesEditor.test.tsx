import assert from "node:assert/strict";
import { test } from "node:test";
import { act, useState } from "react";
import { changeInputValue, deferred, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import type { AccountResponseRules, AccountSnapshot } from "@yinfengwindy/shiori-sdk";
import { AccountResponseRulesEditor } from "./AccountResponseRulesEditor";
import { createAccountClient } from "./accountClient";

const account: AccountSnapshot = {
  id: "a", pluginId: "demo", platform: "demo", platformAccountId: "101", configRef: "demo",
  displayName: "", avatarUrl: "", roleId: "role-1",
  runtimeActive: true, connection: "online", capabilities: [], error: "",
  responseRules: { privateEnabled: true, groupEnabled: true, blockedSenderIds: [] },
};
type Request = { method: string; payload: Record<string, unknown> };

function serializedRules(rules: AccountResponseRules) {
  return { private_enabled: rules.privateEnabled, group_enabled: rules.groupEnabled,
    blocked_sender_ids: rules.blockedSenderIds, ...(rules.allowFullTools ? { allow_full_tools: true } : {}) };
}

/** Real account client and controlled owner; only the bridge transport is replaced. */
async function mountEditor(initial = account, options: { fail?: () => boolean; wait?: () => Promise<void> } = {}) {
  let host = initial;
  let hostRules: unknown = serializedRules(initial.responseRules);
  let publish: (snapshot: AccountSnapshot) => void = () => { throw new Error("Editor is not mounted"); };
  let refreshes = 0;
  const calls: Request[] = [];
  const client = createAccountClient();
  const row = () => ({ id: host.id, plugin_id: host.pluginId, platform: host.platform,
    platform_account_id: host.platformAccountId, config_ref: host.configRef, display_name: host.displayName,
    avatar_url: host.avatarUrl, role_id: host.roleId, runtime_active: host.runtimeActive,
    connection: host.connection, capabilities: host.capabilities, error: host.error, response_rules: hostRules });
  function Owner() {
    const [snapshot, setSnapshot] = useState(initial);
    publish = setSnapshot;
    return <AccountResponseRulesEditor account={snapshot} disabled={false} onChanged={async () => {
      setSnapshot(await client.get(snapshot.id));
      refreshes += 1;
    }} />;
  }
  const view = await mountTestComponent(<Owner />, { windowGlobals: { miraDesktop: {
    invoke: async ({ method, payload }: Request) => {
      if (method === "accounts.rules.set") {
        calls.push({ method, payload });
        const failure = options.fail?.();
        if (!failure) hostRules = payload.response_rules;
        // Capture the operation's response before a later host refresh/rebind.
        const response = failure
          ? { id: "r", type: "response", method, payload: null, error: { code: "rules_failed", message: "插件拒绝保存", details: {} } }
          : { id: "r", type: "response", method, error: null, payload: { account: row() } };
        await options.wait?.();
        return response;
      }
      assert.equal(method, "accounts.get");
      return { id: "r", type: "response", method, error: null, payload: { account: row() } };
    },
  } } });
  return { ...view, calls, refreshes: () => refreshes,
    publish: async (snapshot: AccountSnapshot) => {
      host = snapshot; hostRules = serializedRules(snapshot.responseRules);
      await act(async () => publish(snapshot));
    } };
}

const checkbox = (container: HTMLElement, label: string) => Array.from(container.querySelectorAll("label"))
  .find((item) => item.textContent?.includes(label))?.querySelector<HTMLInputElement>('input[type="checkbox"]');
const permission = (container: HTMLElement) => {
  const toggle = container.querySelector<HTMLButtonElement>('[role="switch"][aria-label="允许完整工具权限"]');
  assert.ok(toggle); return toggle;
};
const blur = async (element: HTMLElement) => act(async () => { element.dispatchEvent(new FocusEvent("focusout", { bubbles: true })); });
const grantedAccount = (): AccountSnapshot => ({ ...account, capabilities: ["groups", "full_tools"],
  responseRules: { ...account.responseRules, allowFullTools: true, blockedSenderIds: ["kept"] } });

test("rules save on their own and subsequent edits use the refreshed host snapshot", async () => {
  const view = await mountEditor({ ...account, capabilities: ["groups"] });
  try {
    assert.equal(view.container.querySelector("button"), null);
    await act(async () => checkbox(view.container, "私聊启用")?.click());
    assert.deepEqual(view.calls[0].payload.response_rules, { private_enabled: false, group_enabled: true, blocked_sender_ids: [] });
    const blocked = view.container.querySelector("textarea"); assert.ok(blocked);
    await changeInputValue(blocked, " sender-1 \n\nsender-2");
    assert.equal(view.calls.length, 1);
    await blur(blocked);
    assert.deepEqual(view.calls[1].payload.response_rules, { private_enabled: false, group_enabled: true, blocked_sender_ids: ["sender-1", "sender-2"] });
    await blur(blocked);
    assert.equal(view.calls.length, 2);
    assert.equal(view.refreshes(), 2);
    assert.doesNotMatch(view.container.textContent ?? "", /已保存/);
  } finally { await view.cleanup(); }
});

test("failed saves expose the error and show the current host rules", async () => {
  let failing = true;
  const view = await mountEditor({ ...account, capabilities: ["groups"], responseRules: {
    ...account.responseRules, blockedSenderIds: ["kept"],
  } }, { fail: () => failing });
  try {
    await act(async () => checkbox(view.container, "群聊启用")?.click());
    assert.match(view.container.textContent ?? "", /插件拒绝保存/);
    assert.equal(checkbox(view.container, "群聊启用")?.checked, true);
    const blocked = view.container.querySelector("textarea"); assert.ok(blocked);
    await changeInputValue(blocked, "other");
    await blur(blocked);
    assert.equal(blocked.value, "kept");
    failing = false;
    await act(async () => checkbox(view.container, "群聊启用")?.click());
    assert.doesNotMatch(view.container.textContent ?? "", /插件拒绝保存/);
    assert.equal(checkbox(view.container, "群聊启用")?.checked, false);
  } finally { await view.cleanup(); }
});

test("capability controls remain scoped to the current account", async () => {
  const view = await mountEditor();
  try {
    assert.match(view.container.textContent ?? "", /私聊启用.*黑名单成员 ID/);
    assert.doesNotMatch(view.container.textContent ?? "", /群聊|允许完整工具权限/);
    await view.publish({ ...account, capabilities: ["groups"] });
    assert.match(view.container.textContent ?? "", /群聊启用/);
    assert.doesNotMatch(view.container.textContent ?? "", /需要 @|允许完整工具权限/);
  } finally { await view.cleanup(); }
});

test("full tool permission defaults off and a failed revocation keeps the host grant", async () => {
  let failing = false;
  const view = await mountEditor({ ...account, capabilities: ["full_tools"] }, { fail: () => failing });
  try {
    const toggle = permission(view.container);
    assert.equal(toggle.getAttribute("aria-checked"), "false");
    await act(async () => toggle.click());
    assert.equal(toggle.getAttribute("aria-checked"), "true");
    await act(async () => checkbox(view.container, "私聊启用")?.click());
    assert.deepEqual(view.calls[1].payload.response_rules, { private_enabled: false, group_enabled: true, blocked_sender_ids: [], allow_full_tools: true });
    failing = true;
    await act(async () => toggle.click());
    assert.equal(toggle.getAttribute("aria-checked"), "true");
    failing = false;
    await act(async () => toggle.click());
    assert.equal(toggle.getAttribute("aria-checked"), "false");
    assert.deepEqual(view.calls.at(-1)?.payload.response_rules, { private_enabled: false, group_enabled: true, blocked_sender_ids: [] });
  } finally { await view.cleanup(); }
});

test("fixed-peer accounts use activation for admission and retain only the tool grant", async () => {
  const view = await mountEditor({ ...account, capabilities: ["fixed_peer", "full_tools"] });
  try {
    assert.doesNotMatch(view.container.textContent ?? "", /私聊启用|群聊启用|黑名单/);
    assert.equal(view.container.querySelector("textarea"), null);
    await act(async () => permission(view.container).click());
    assert.deepEqual(view.calls[0].payload.response_rules, { private_enabled: true, group_enabled: true, blocked_sender_ids: [], allow_full_tools: true });
    await view.publish(account);
    assert.match(view.container.textContent ?? "", /私聊启用.*黑名单成员 ID/);
  } finally { await view.cleanup(); }
});

test("a same-ID host revocation replaces the baseline without losing a dirty blacklist", async () => {
  const initial = grantedAccount();
  const view = await mountEditor(initial);
  try {
    const blocked = view.container.querySelector("textarea"); assert.ok(blocked);
    await changeInputValue(blocked, " draft-peer \n");
    await view.publish({ ...initial, responseRules: { ...initial.responseRules, allowFullTools: false } });
    assert.equal(permission(view.container).getAttribute("aria-checked"), "false");
    assert.equal(blocked.value, " draft-peer \n");
    await act(async () => checkbox(view.container, "私聊启用")?.click());
    assert.deepEqual(view.calls[0].payload.response_rules, { private_enabled: false, group_enabled: true, blocked_sender_ids: ["kept"] });
    assert.equal(blocked.value, " draft-peer \n");
    await blur(blocked);
    assert.deepEqual(view.calls[1].payload.response_rules, { private_enabled: false, group_enabled: true, blocked_sender_ids: ["draft-peer"] });
    assert.equal(permission(view.container).getAttribute("aria-checked"), "false");
  } finally { await view.cleanup(); }
});

for (const failing of [false, true]) {
  for (const saveBlacklist of [false, true]) {
    test(`new host rules win over a late ${failing ? "failure" : "success"} for ${saveBlacklist ? "blacklist" : "toggle"} save`, async () => {
      const gate = deferred<void>();
      const initial = grantedAccount();
      const view = await mountEditor(initial, { fail: () => failing, wait: () => gate.promise });
      try {
        const blocked = view.container.querySelector("textarea"); assert.ok(blocked);
        await changeInputValue(blocked, "draft-peer");
        if (saveBlacklist) await blur(blocked);
        else await act(async () => checkbox(view.container, "群聊启用")?.click());
        assert.equal(view.calls.length, 1);
        assert.equal(blocked.disabled, true);
        await view.publish({ ...initial, responseRules: { ...initial.responseRules, allowFullTools: false, blockedSenderIds: ["new-host"] } });
        assert.equal(permission(view.container).getAttribute("aria-checked"), "false");
        assert.equal(blocked.disabled, true);
        await act(async () => gate.resolve());
        assert.equal(permission(view.container).getAttribute("aria-checked"), "false");
        assert.equal(blocked.disabled, false);
        assert.equal(blocked.value, saveBlacklist ? "new-host" : "draft-peer");
        await act(async () => checkbox(view.container, "私聊启用")?.click());
        assert.deepEqual(view.calls.at(-1)?.payload.response_rules, { private_enabled: false, group_enabled: true, blocked_sender_ids: ["new-host"] });
      } finally { gate.resolve(); await view.cleanup(); }
    });
  }
}

test("an unchanged-value new host snapshot also supersedes an old pending enable", async () => {
  const gate = deferred<void>();
  const initial = { ...account, capabilities: ["full_tools"] };
  const view = await mountEditor(initial, { wait: () => gate.promise });
  try {
    await act(async () => permission(view.container).click());
    assert.equal(permission(view.container).getAttribute("aria-checked"), "true");
    await view.publish({ ...initial, responseRules: { ...initial.responseRules } });
    assert.equal(permission(view.container).getAttribute("aria-checked"), "false");
    await act(async () => gate.resolve());
    assert.equal(permission(view.container).getAttribute("aria-checked"), "false");
  } finally { gate.resolve(); await view.cleanup(); }
});
