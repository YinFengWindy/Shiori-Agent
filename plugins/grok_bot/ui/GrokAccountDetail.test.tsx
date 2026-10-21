import assert from "node:assert/strict";
import { it } from "node:test";
import { act } from "react";
import type { AccountSnapshot } from "@yinfengwindy/shiori-sdk";
import { changeInputValue, createFakeHostServices, createFakePluginClient, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { GrokAccountDetail } from "./GrokAccountDetail";

it("saves only this role's webhook and clears credentials after saving", async () => {
  const requests: Array<{ method: string; payload?: Record<string, unknown> }> = [];
  const client = createFakePluginClient({ call: async <T,>(method: string, payload?: Record<string, unknown>) => {
    requests.push({ method, payload });
    return { account_id: "grok_bot:one" } as T;
  } });
  let changed = "";
  const view = await mountTestComponent(<GrokAccountDetail account={null} roleId="mira" client={client} host={createFakeHostServices().host} onChanged={(id) => { changed = id ?? ""; }} />);
  try {
    const webhook = document.querySelector<HTMLInputElement>('input[type="url"]');
    const secret = document.querySelector<HTMLInputElement>('input[type="password"]');
    assert.ok(webhook && secret);
    await changeInputValue(webhook, "https://example.test/webhook");
    await changeInputValue(secret, "secret");
    await act(async () => Array.from(document.querySelectorAll("button")).find((button) => button.textContent === "连接")?.click());
    assert.deepEqual(requests, [{ method: "account.save", payload: { role_id: "mira", webhook_url: "https://example.test/webhook", webhook_key: "secret", max_messages: 12 } }]);
    assert.equal(changed, "grok_bot:one");
    assert.equal(secret.value, "");
    assert.equal(document.body.textContent?.includes("放开权限"), false);
  } finally {
    await view.cleanup();
    await client.dispose();
  }
});

it("shows activation and routine setup without message monitoring or reset controls", async () => {
  const requests: string[] = [];
  const routine = "本机配置 C:/plugin/client.ps1 C:/workspace/client.json";
  const client = createFakePluginClient({ call: async <T,>(method: string) => {
    requests.push(method);
    return { webhook_url: "https://example.test/hook", has_key: true, enabled: true, max_messages: 12, routine_config: routine,
      last_status: "Grok 已接收，等待回复", exchange_count: 12, verified: true } as T;
  } });
  const account: AccountSnapshot = {
    id: "grok_bot:one", pluginId: "grok_bot", platform: "grok_bot", platformAccountId: "one", configRef: "one", displayName: "Grok Bot", avatarUrl: "", roleId: "mira", runtimeActive: true, connection: "online", capabilities: ["fixed_peer", "full_tools", "private"], error: "",
    responseRules: { privateEnabled: true, groupEnabled: false, blockedSenderIds: [] },
  };
  const view = await mountTestComponent(<GrokAccountDetail account={account} roleId="mira" client={client} host={createFakeHostServices().host} onChanged={() => undefined} />);
  try {
    assert.match(document.body.textContent ?? "", /已启用/);
    assert.match(document.body.textContent ?? "", /单次交流消息上限/);
    assert.doesNotMatch(document.body.textContent ?? "", /回程已验证|等待回程|等待回复|继续新一轮|12 \/ 12/);
    assert.equal(document.querySelector<HTMLTextAreaElement>('textarea[aria-label="Routine 配置内容"]')?.value, routine);
    assert.equal(document.querySelector<HTMLInputElement>('input[type="password"]')?.value, "");
    assert.deepEqual(requests, ["account.detail"]);
  } finally {
    await view.cleanup();
    await client.dispose();
  }
});
