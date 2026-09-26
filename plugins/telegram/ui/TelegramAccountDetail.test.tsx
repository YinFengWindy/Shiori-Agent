import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { changeInputValue, mountTestComponent } from "../../../apps/desktop/renderer/src/shared/testing/domTestHarness";
import type { AccountSnapshot } from "../../../apps/desktop/renderer/src/accounts/accountClient";
import type { PluginRpcClient } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";
import { desktopPluginHostServices } from "../../../apps/desktop/renderer/src/plugins/pluginHostServices";
import { TelegramAccountDetail } from "./TelegramAccountDetail";

const account: AccountSnapshot = {
  id: "account-1", pluginId: "telegram", platform: "telegram", platformAccountId: "123", configRef: "legacy",
  displayName: "First Bot", avatarUrl: "", roleId: null, pluginEnabled: true,
  runtimeActive: true, connection: "online", capabilities: [], knownCapabilities: [], error: "",
  responseRules: { privateEnabled: true, groupEnabled: true, requireMention: true, blockedSenderIds: [], groupRules: [] },
};

test("Token draft verifies before the legacy account configuration changes", async () => {
  const calls: string[] = [];
  const submissions: Record<string, unknown>[] = [];
  let rejectVerification = true;
  let changedId = "";
  const client = { call: async (name: string) => {
    calls.push(name);
    if (name === "known.list") return { chats: [] };
    if (rejectVerification) throw new Error("invalid Token");
    return { bot_id: "123" };
  } } as PluginRpcClient;
  const view = await mountTestComponent(
    <TelegramAccountDetail account={account} onChanged={(id) => { changedId = id ?? ""; }} client={client} host={desktopPluginHostServices} />,
    { windowGlobals: { miraDesktop: { invoke: async ({ method, payload }: { method: string; payload: Record<string, unknown> }) => {
      calls.push(method);
      if (method === "plugin.config.set") submissions.push(payload.values as Record<string, unknown>);
      return { id: "response", type: "response", method, error: null, payload: method === "plugin.config.get"
        ? { plugin_id: "telegram", schema: null, values: { token: "123:old", bots: [] }, env_status: {} }
        : { plugin_id: "telegram", values: submissions.at(-1), env_status: {}, generation: 2 } };
    } } } },
  );
  try {
    const input = view.container.querySelector<HTMLInputElement>('input[type="password"]');
    assert.ok(input);
    await changeInputValue(input, "123:new");
    assert.equal(submissions.length, 0);
    const save = () => Array.from(view.container.querySelectorAll<HTMLButtonElement>("button"))
      .find((button) => button.textContent === "保存并连接");
    await act(async () => save()?.click());
    assert.equal(submissions.length, 0);
    rejectVerification = false;
    await act(async () => save()?.click());
    assert.equal(submissions[0]?.token, "");
    assert.deepEqual(submissions[0]?.bots, [{ ref: "legacy", token: "123:new", enabled: true }]);
    assert.equal(changedId, "account-1");
    assert.deepEqual(calls.filter((name) => name === "plugin.config.set"), ["plugin.config.set"]);
  } finally {
    await view.cleanup();
  }
});
