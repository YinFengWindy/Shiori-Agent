import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { changeInputValue, mountTestComponent } from "../shared/testing/domTestHarness";
import { AccountResponseRulesEditor } from "./AccountResponseRulesEditor";
import type { AccountSnapshot } from "./accountClient";

const account: AccountSnapshot = {
  id: "a", pluginId: "demo", platform: "demo", platformAccountId: "101",
  displayName: "", avatarUrl: "", roleId: null, pluginEnabled: true,
  runtimeActive: true, connection: "online", capabilities: [], knownCapabilities: [], error: "",
  responseRules: { privateEnabled: true, groupEnabled: true, requireMention: true,
    blockedSenderIds: [], groupRules: [{ chatId: "group-1", enabled: true,
      requireMention: true, blockedSenderIds: [] }] },
};

test("group response changes stay in draft until explicit save and retain raw chat identity", async () => {
  const calls: Array<{ method: string; payload: Record<string, unknown> }> = [];
  let refreshes = 0;
  const view = await mountTestComponent(
    <AccountResponseRulesEditor account={account} onChanged={() => { refreshes += 1; }} />,
    { windowGlobals: { miraDesktop: { invoke: async ({ method, payload }: { method: string; payload: Record<string, unknown> }) => {
      calls.push({ method, payload });
      return { id: "response", type: "response", method, error: null, payload: { account: {
        id: "a", plugin_id: "demo", platform: "demo", platform_account_id: "101",
        display_name: "", avatar_url: "", role_id: null, plugin_enabled: true,
        runtime_active: true, connection: "online", capabilities: [], known_capabilities: [], error: "",
        response_rules: payload.response_rules,
      } } };
    } } } },
  );
  try {
    const groupId = view.container.querySelector<HTMLInputElement>('[aria-label="群 1 会话 ID"]');
    assert.ok(groupId);
    await changeInputValue(groupId, "group-2");
    assert.equal(calls.length, 0);
    const save = Array.from(view.container.querySelectorAll<HTMLButtonElement>("button")).find((button) => button.textContent === "保存规则");
    assert.ok(save);
    await act(async () => save.click());
    assert.equal(calls[0].method, "accounts.rules.set");
    const rules = calls[0].payload.response_rules as { group_rules: Array<{ chat_id: string }> };
    assert.equal(rules.group_rules[0].chat_id, "group-2");
    assert.equal(refreshes, 1);
  } finally { await view.cleanup(); }
});

test("private-only accounts hide group controls but retained group rules stay available offline", async () => {
  const view = await mountTestComponent(
    <AccountResponseRulesEditor account={{ ...account, responseRules: { ...account.responseRules, groupRules: [] } }} onChanged={() => undefined} />,
  );
  try {
    assert.match(view.container.textContent ?? "", /私聊启用/);
    assert.doesNotMatch(view.container.textContent ?? "", /群聊启用|群规则|黑名单/);
    await view.render(<AccountResponseRulesEditor key="offline" account={{ ...account, pluginEnabled: false, runtimeActive: false }} onChanged={() => undefined} />);
    assert.match(view.container.textContent ?? "", /群规则/);
    assert.equal(view.container.querySelector<HTMLInputElement>('[aria-label="群 1 会话 ID"]')?.value, "group-1");
    await view.render(<AccountResponseRulesEditor key="offline-default" account={{ ...account,
      pluginEnabled: false, runtimeActive: false,
      responseRules: { ...account.responseRules, groupRules: [], requireMention: false },
    }} onChanged={() => undefined} />);
    assert.match(view.container.textContent ?? "", /群聊需要 @/);
    const mention = Array.from(view.container.querySelectorAll("label")).find((label) => label.textContent?.includes("群聊需要 @"));
    assert.equal(mention?.querySelector<HTMLInputElement>('input[type="checkbox"]')?.checked, false);
    await view.render(<AccountResponseRulesEditor key="offline-known" account={{ ...account,
      pluginEnabled: false, runtimeActive: false, capabilities: [], knownCapabilities: ["groups"],
      responseRules: { ...account.responseRules, groupRules: [] },
    }} onChanged={() => undefined} />);
    assert.match(view.container.textContent ?? "", /群聊启用|群规则/);
  } finally { await view.cleanup(); }
});
