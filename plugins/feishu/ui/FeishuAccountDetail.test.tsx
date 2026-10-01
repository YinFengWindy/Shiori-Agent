import assert from "node:assert/strict";
import { it } from "node:test";
import { act } from "react";
import type { AccountSnapshot } from "@shiori/sdk";
import { changeInputValue, createFakeHostServices, createFakePluginClient, mountTestComponent } from "@shiori/sdk/testing";
import { FeishuAccountDetail } from "./FeishuAccountDetail";

type Request = { method: string; payload?: Record<string, unknown> };

function button(label: string) {
  return Array.from(document.querySelectorAll<HTMLButtonElement>("button")).find((item) => item.textContent === label);
}

it("saves a new app for the adding role through the plugin and shows a refusal", async () => {
  const requests: Request[] = [];
  let refuse = true;
  const client = createFakePluginClient({ call: async <T,>(method: string, payload?: Record<string, unknown>) => {
    requests.push({ method, payload });
    if (method === "accounts.save" && refuse) throw new Error("bad credential");
    return (method === "accounts.save" ? { account_id: "feishu:feishu:cli_new" } : {}) as T;
  } });
  const fake = createFakeHostServices();
  let created = "";
  const view = await mountTestComponent(
    <FeishuAccountDetail account={null} roleId="mira" onChanged={(id) => { created = id ?? ""; }} client={client} host={fake.host} />,
  );
  try {
    const id = document.querySelector<HTMLInputElement>('input[autocomplete="off"]');
    const secret = document.querySelector<HTMLInputElement>('input[type="password"]');
    assert.ok(id && secret);
    await changeInputValue(id, "cli_new");
    await changeInputValue(secret, "draft-secret");
    await act(async () => button("连接")?.click());
    assert.match(document.body.textContent ?? "", /bad credential/);
    assert.equal(created, "");

    refuse = false;
    await act(async () => button("连接")?.click());
    const saves = requests.filter((item) => item.method === "accounts.save");
    assert.deepEqual(saves.at(-1)?.payload, { role_id: "mira", domain: "feishu", app_id: "cli_new", app_secret: "draft-secret" });
    assert.equal(created, "feishu:feishu:cli_new");
    // The app is saved through the plugin, never written into the plugin's config.
    assert.equal(requests.some((item) => item.method.startsWith("config.")), false);
    assert.equal(fake.calls.some((call) => call.service.startsWith("config.")), false);
  } finally {
    await view.cleanup();
    await client.dispose();
  }
});

it("disconnects an online app through the plugin", async () => {
  const requests: Request[] = [];
  const client = createFakePluginClient({ call: async <T,>(method: string, payload?: Record<string, unknown>) => {
    requests.push({ method, payload });
    return (method === "accounts.profile" ? { identity: {}, targets: [] } : {}) as T;
  } });
  const account: AccountSnapshot = {
    id: "feishu:feishu:cli_a", pluginId: "feishu", platform: "feishu", platformAccountId: "feishu:cli_a", configRef: "feishu:cli_a",
    displayName: "A", avatarUrl: "", roleId: "mira", runtimeActive: true,
    connection: "online", capabilities: ["private"], error: "",
    responseRules: { privateEnabled: true, groupEnabled: false, blockedSenderIds: [] },
  };
  const view = await mountTestComponent(
    <FeishuAccountDetail account={account} roleId="mira" onChanged={() => undefined} client={client} host={createFakeHostServices().host} />,
  );
  try {
    const id = document.querySelector<HTMLInputElement>('input[autocomplete="off"]');
    assert.equal(id?.value, "cli_a");
    await act(async () => button("断开连接")?.click());
    assert.deepEqual(requests.find((item) => item.method === "accounts.disconnect")?.payload,
      { account_id: "feishu:feishu:cli_a", role_id: "mira" });
  } finally {
    await view.cleanup();
    await client.dispose();
  }
});
