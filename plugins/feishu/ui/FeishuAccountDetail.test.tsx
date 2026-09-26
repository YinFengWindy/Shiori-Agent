import assert from "node:assert/strict";
import { it } from "node:test";
import { act } from "react";
import { createPluginRpcClient } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";
import { desktopPluginHostServices } from "../../../apps/desktop/renderer/src/plugins/pluginHostServices";
import type { AccountSnapshot } from "../../../apps/desktop/renderer/src/accounts/accountClient";
import { changeInputValue, mountTestComponent } from "../../../apps/desktop/renderer/src/shared/testing/domTestHarness";
import { FeishuAccountDetail } from "./FeishuAccountDetail";

it("keeps a credential draft offline until verification and explicit save", async () => {
  const calls: string[] = [];
  let allowVerification = false;
  const invoke = async ({ method, payload: requestPayload }: { method: string; payload: Record<string, unknown> }) => {
    calls.push(method);
    if (method === "plugin.feishu.accounts.verify" && !allowVerification) throw new Error("bad credential");
    const payload = method === "plugin.config.get"
      ? { values: { app_id: "", app_secret: "", domain: "feishu", accounts: [] }, schema: null, env_status: {} }
      : method === "plugins.communication.open" ? { generation: "test" }
        : method === "plugin.config.set" ? { values: requestPayload.values }
        : method === "accounts.list" ? { accounts: [{
          id: "new-account", plugin_id: "feishu", platform: "feishu", platform_account_id: "feishu:cli_new",
          display_name: "", avatar_url: "", role_id: null, plugin_enabled: true, runtime_active: true,
          connection: "connecting", capabilities: [], known_capabilities: [], error: "",
          response_rules: { private_enabled: true, group_enabled: true, require_mention: true, blocked_sender_ids: [], group_rules: [] },
        }] } : {};
    return { id: "response", type: "response" as const, method, error: null, payload };
  };
  const client = createPluginRpcClient("feishu", invoke);
  let created = "";
  const view = await mountTestComponent(
    <FeishuAccountDetail account={null} onChanged={(id) => { created = id ?? ""; }} client={client} host={desktopPluginHostServices} />,
    { windowGlobals: { miraDesktop: { invoke, onEvent: () => () => undefined } } },
  );
  try {
    const id = document.querySelector<HTMLInputElement>('input[autocomplete="off"]');
    const secret = document.querySelector<HTMLInputElement>('input[type="password"]');
    assert.ok(id);
    assert.ok(secret);
    const save = () => Array.from(document.querySelectorAll<HTMLButtonElement>("button"))
      .find((button) => button.textContent === "保存并连接");
    await changeInputValue(id, "cli_new");
    await changeInputValue(secret, "draft-secret");
    assert.equal(calls.includes("plugin.config.set"), false);
    await act(async () => save()?.click());
    assert.equal(calls.includes("plugin.config.set"), false);
    assert.match(document.body.textContent ?? "", /bad credential/);

    allowVerification = true;
    await act(async () => save()?.click());
    assert.equal(calls.includes("plugin.config.set"), true);
    assert.equal(created, "new-account");
  } finally {
    await view.cleanup();
    await client.dispose();
  }
});

it("disconnects an online app through the explicit account control", async () => {
  const configured = { app_id: "", app_secret: "", domain: "feishu", accounts: [
    { app_id: "cli_a", app_secret: "saved", domain: "feishu", connection_enabled: true },
  ] };
  let submitted: unknown = null;
  const invoke = async ({ method, payload }: { method: string; payload: Record<string, unknown> }) => {
    if (method === "plugin.config.set") submitted = payload.values;
    const result = method === "plugin.config.get" ? { values: configured, schema: null, env_status: {} }
      : method === "plugin.config.set" ? { values: submitted }
        : method === "plugins.communication.open" ? { generation: "test" }
          : method === "plugin.feishu.accounts.profile" ? { identity: {}, targets: [] } : {};
    return { id: "response", type: "response" as const, method, error: null, payload: result };
  };
  const client = createPluginRpcClient("feishu", invoke);
  const account: AccountSnapshot = {
    id: "account-a", pluginId: "feishu", platform: "feishu", platformAccountId: "feishu:cli_a",
    displayName: "A", avatarUrl: "", roleId: null, pluginEnabled: true, runtimeActive: true,
    connection: "online", capabilities: ["private"], knownCapabilities: ["private"], error: "",
    responseRules: { privateEnabled: true, groupEnabled: false, requireMention: false, blockedSenderIds: [], groupRules: [] },
  };
  const view = await mountTestComponent(
    <FeishuAccountDetail account={account} onChanged={() => undefined} client={client} host={desktopPluginHostServices} />,
    { windowGlobals: { miraDesktop: { invoke, onEvent: () => () => undefined } } },
  );
  try {
    const disconnect = () => Array.from(document.querySelectorAll<HTMLButtonElement>("button"))
      .find((button) => button.textContent === "断开连接");
    assert.ok(disconnect());
    await act(async () => disconnect()?.click());
    const accountConfigs = submitted && typeof submitted === "object" && "accounts" in submitted ? submitted.accounts : undefined;
    assert.ok(Array.isArray(accountConfigs));
    assert.equal(accountConfigs[0].connection_enabled, false);
  } finally {
    await view.cleanup();
    await client.dispose();
  }
});
