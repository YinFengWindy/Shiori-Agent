import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { changeInputValue, mountTestComponent } from "../shared/testing/domTestHarness";
import { AccountResponseRulesEditor } from "./AccountResponseRulesEditor";
import type { AccountSnapshot } from "./accountClient";

const account: AccountSnapshot = {
  id: "a", pluginId: "demo", platform: "demo", platformAccountId: "101", configRef: "demo",
  displayName: "", avatarUrl: "", roleId: "role-1",
  runtimeActive: true, connection: "online", capabilities: [], error: "",
  responseRules: { privateEnabled: true, groupEnabled: true, requireMention: true, blockedSenderIds: [] },
};

test("blacklist edits stay in draft until explicit save and are trimmed on save", async () => {
  const calls: Array<{ method: string; payload: Record<string, unknown> }> = [];
  let refreshes = 0;
  const view = await mountTestComponent(
    <AccountResponseRulesEditor account={{ ...account, capabilities: ["groups"] }} onChanged={() => { refreshes += 1; }} />,
    { windowGlobals: { miraDesktop: { invoke: async ({ method, payload }: { method: string; payload: Record<string, unknown> }) => {
      calls.push({ method, payload });
      return { id: "response", type: "response", method, error: null, payload: { account: {
        id: "a", plugin_id: "demo", platform: "demo", platform_account_id: "101",
        display_name: "", avatar_url: "", role_id: "role-1",
        runtime_active: true, connection: "online", capabilities: [], error: "",
        response_rules: payload.response_rules,
      } } };
    } } } },
  );
  try {
    const blocked = view.container.querySelector("textarea");
    assert.ok(blocked);
    await changeInputValue(blocked, " sender-1 \n\nsender-2");
    assert.equal(calls.length, 0);
    const save = Array.from(view.container.querySelectorAll<HTMLButtonElement>("button")).find((button) => button.textContent === "保存规则");
    assert.ok(save);
    await act(async () => save.click());
    assert.equal(calls[0].method, "accounts.rules.set");
    assert.deepEqual(calls[0].payload.response_rules, { private_enabled: true, group_enabled: true,
      require_mention: true, blocked_sender_ids: ["sender-1", "sender-2"] });
    assert.equal(refreshes, 1);
  } finally { await view.cleanup(); }
});

test("group controls show for group-capable accounts or retained non-default group settings, even offline", async () => {
  const view = await mountTestComponent(
    <AccountResponseRulesEditor account={account} onChanged={() => undefined} />,
  );
  try {
    assert.match(view.container.textContent ?? "", /私聊启用/);
    assert.doesNotMatch(view.container.textContent ?? "", /群聊启用|黑名单/);
    await view.render(<AccountResponseRulesEditor key="offline-default" account={{ ...account,
      runtimeActive: false,
      responseRules: { ...account.responseRules, requireMention: false },
    }} onChanged={() => undefined} />);
    assert.match(view.container.textContent ?? "", /群聊需要 @/);
    const mention = Array.from(view.container.querySelectorAll("label")).find((label) => label.textContent?.includes("群聊需要 @"));
    assert.equal(mention?.querySelector<HTMLInputElement>('input[type="checkbox"]')?.checked, false);
    await view.render(<AccountResponseRulesEditor key="online-groups" account={{ ...account,
      capabilities: ["groups"],
    }} onChanged={() => undefined} />);
    assert.match(view.container.textContent ?? "", /群聊启用/);
  } finally { await view.cleanup(); }
});
