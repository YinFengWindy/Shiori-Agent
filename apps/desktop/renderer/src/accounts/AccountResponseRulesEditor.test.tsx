import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { changeInputValue, mountTestComponent } from "@shiori/plugin-sdk/testing";
import { AccountResponseRulesEditor } from "./AccountResponseRulesEditor";
import type { AccountSnapshot } from "@shiori/plugin-sdk";

const account: AccountSnapshot = {
  id: "a", pluginId: "demo", platform: "demo", platformAccountId: "101", configRef: "demo",
  displayName: "", avatarUrl: "", roleId: "role-1",
  runtimeActive: true, connection: "online", capabilities: [], error: "",
  responseRules: { privateEnabled: true, groupEnabled: true, blockedSenderIds: [] },
};

type Request = { method: string; payload: Record<string, unknown> };

function desktop(calls: Request[], fail: () => boolean) {
  return { windowGlobals: { miraDesktop: { invoke: async ({ method, payload }: Request) => {
    calls.push({ method, payload });
    if (fail()) return { id: "response", type: "response", method, payload: null,
      error: { code: "rules_failed", message: "插件拒绝保存", details: {} } };
    return { id: "response", type: "response", method, error: null, payload: { account: {
      id: "a", plugin_id: "demo", platform: "demo", platform_account_id: "101", config_ref: "demo",
      display_name: "", avatar_url: "", role_id: "role-1",
      runtime_active: true, connection: "online", capabilities: [], error: "",
      response_rules: payload.response_rules,
    } } };
  } } } };
}

const checkbox = (container: HTMLElement, label: string) => Array.from(container.querySelectorAll("label"))
  .find((item) => item.textContent?.includes(label))?.querySelector<HTMLInputElement>('input[type="checkbox"]');

test("rules save on their own: a checkbox at once, the trimmed blacklist on blur, without a save button", async () => {
  const calls: Request[] = [];
  let refreshes = 0;
  const view = await mountTestComponent(
    <AccountResponseRulesEditor account={{ ...account, capabilities: ["groups"] }} onChanged={() => { refreshes += 1; }} />,
    desktop(calls, () => false),
  );
  try {
    assert.equal(view.container.querySelector("button"), null);
    await act(async () => checkbox(view.container, "私聊启用")?.click());
    assert.deepEqual(calls[0].payload.response_rules, { private_enabled: false, group_enabled: true,
      blocked_sender_ids: [] });

    const blocked = view.container.querySelector("textarea");
    assert.ok(blocked);
    await changeInputValue(blocked, " sender-1 \n\nsender-2");
    assert.equal(calls.length, 1, "typing does not save");
    await act(async () => blocked.dispatchEvent(new FocusEvent("focusout", { bubbles: true })));
    assert.deepEqual(calls[1].payload.response_rules, { private_enabled: false, group_enabled: true,
      blocked_sender_ids: ["sender-1", "sender-2"] });
    // Leaving the field again without a change saves nothing.
    await act(async () => blocked.dispatchEvent(new FocusEvent("focusout", { bubbles: true })));
    assert.equal(calls.length, 2);
    assert.equal(refreshes, 2);
    assert.doesNotMatch(view.container.textContent ?? "", /已保存/);
  } finally { await view.cleanup(); }
});

test("a failed save shows why and puts the last saved value back", async () => {
  const calls: Request[] = [];
  let failing = true;
  const view = await mountTestComponent(
    <AccountResponseRulesEditor account={{ ...account, capabilities: ["groups"], responseRules: {
      ...account.responseRules, blockedSenderIds: ["kept"],
    } }} onChanged={() => undefined} />,
    desktop(calls, () => failing),
  );
  try {
    await act(async () => checkbox(view.container, "群聊启用")?.click());
    assert.equal(calls.length, 1);
    assert.match(view.container.textContent ?? "", /插件拒绝保存/);
    assert.equal(checkbox(view.container, "群聊启用")?.checked, true);

    const blocked = view.container.querySelector("textarea");
    assert.ok(blocked);
    await changeInputValue(blocked, "other");
    await act(async () => blocked.dispatchEvent(new FocusEvent("focusout", { bubbles: true })));
    assert.equal(view.container.querySelector("textarea")?.value, "kept");

    failing = false;
    await act(async () => checkbox(view.container, "群聊启用")?.click());
    assert.doesNotMatch(view.container.textContent ?? "", /插件拒绝保存/);
    assert.equal(checkbox(view.container, "群聊启用")?.checked, false);
  } finally { await view.cleanup(); }
});

test("the group toggle shows only for group-capable accounts, the blacklist always", async () => {
  const view = await mountTestComponent(
    <AccountResponseRulesEditor account={account} onChanged={() => undefined} />,
  );
  try {
    assert.match(view.container.textContent ?? "", /私聊启用/);
    assert.match(view.container.textContent ?? "", /黑名单成员 ID/);
    assert.doesNotMatch(view.container.textContent ?? "", /群聊/);
    await view.render(<AccountResponseRulesEditor key="groups" account={{ ...account,
      capabilities: ["groups"],
    }} onChanged={() => undefined} />);
    assert.match(view.container.textContent ?? "", /群聊启用/);
    assert.doesNotMatch(view.container.textContent ?? "", /需要 @/);
    assert.match(view.container.textContent ?? "", /黑名单成员 ID/);
  } finally { await view.cleanup(); }
});
