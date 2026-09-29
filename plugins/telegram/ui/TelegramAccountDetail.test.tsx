import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { changeInputValue, mountTestComponent } from "../../../apps/desktop/renderer/src/shared/testing/domTestHarness";
import type { AccountSnapshot } from "../../../apps/desktop/renderer/src/accounts/accountClient";
import type { PluginRpcClient } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";
import { pluginHostServicesFor } from "../../../apps/desktop/renderer/src/plugins/pluginHostServices";
import { TelegramAccountDetail } from "./TelegramAccountDetail";

const account: AccountSnapshot = {
  id: "telegram:123", pluginId: "telegram", platform: "telegram", platformAccountId: "123", configRef: "123",
  displayName: "First Bot", avatarUrl: "", roleId: "mira",
  runtimeActive: true, connection: "online", capabilities: [], error: "",
  responseRules: { privateEnabled: true, groupEnabled: true, requireMention: true, blockedSenderIds: [] },
};

type Call = { name: string; payload?: Record<string, unknown> };

function rpc(calls: Call[], fail = () => false) {
  return { call: async (name: string, payload?: Record<string, unknown>) => {
    calls.push({ name, payload });
    if (name === "known.list") return { chats: [] };
    if (name === "identity.get") return {};
    if (fail()) throw new Error("Bot Token 验证失败");
    return { account_id: "telegram:456" };
  } } as PluginRpcClient;
}

const button = (container: HTMLElement, label: string) => Array.from(container.querySelectorAll<HTMLButtonElement>("button"))
  .find((item) => item.textContent === label);

test("a new Bot is saved for the role through the plugin, and a failure stays in the form", async () => {
  const calls: Call[] = [];
  let failing = true;
  let changedId = "";
  const view = await mountTestComponent(
    <TelegramAccountDetail account={null} roleId="mira" onChanged={(id) => { changedId = id ?? ""; }}
      client={rpc(calls, () => failing)} host={pluginHostServicesFor("telegram")} />,
  );
  try {
    const input = view.container.querySelector<HTMLInputElement>('input[type="password"]');
    assert.ok(input);
    await changeInputValue(input, "456:new");
    await act(async () => button(view.container, "连接")?.click());
    assert.match(view.container.textContent ?? "", /验证失败/);
    assert.equal(changedId, "");
    failing = false;
    await act(async () => button(view.container, "连接")?.click());
    assert.deepEqual(calls.at(-1), { name: "bot.save", payload: { role_id: "mira", token: "456:new" } });
    assert.equal(changedId, "telegram:456");
  } finally {
    await view.cleanup();
  }
});

test("a connected Bot is disconnected, an offline one reconnects without a new Token", async () => {
  const calls: Call[] = [];
  const online = await mountTestComponent(
    <TelegramAccountDetail account={account} roleId="mira" onChanged={() => undefined}
      client={rpc(calls)} host={pluginHostServicesFor("telegram")} />,
  );
  try {
    await act(async () => button(online.container, "断开连接")?.click());
    assert.deepEqual(calls.at(-1), { name: "bot.disconnect", payload: { account_id: "telegram:123", role_id: "mira" } });
  } finally {
    await online.cleanup();
  }
  const offline = await mountTestComponent(
    <TelegramAccountDetail account={{ ...account, connection: "offline" }} roleId="mira" onChanged={() => undefined}
      client={rpc(calls)} host={pluginHostServicesFor("telegram")} />,
  );
  try {
    await act(async () => button(offline.container, "连接")?.click());
    assert.deepEqual(calls.at(-1), { name: "bot.save", payload: { role_id: "mira", token: "", account_id: "telegram:123" } });
  } finally {
    await offline.cleanup();
  }
});
