import assert from "node:assert/strict";
import { it } from "node:test";
import { act } from "react";
import { createPluginRpcClient } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";
import { desktopPluginHostServices } from "../../../apps/desktop/renderer/src/plugins/pluginHostServices";
import type { AccountSnapshot } from "../../../apps/desktop/renderer/src/accounts/accountClient";
import { changeInputValue, mountTestComponent } from "../../../apps/desktop/renderer/src/shared/testing/domTestHarness";
import { FeishuAccountDetail } from "./FeishuAccountDetail";

type Request = { method: string; payload: Record<string, unknown> };

/** The request payload without the host's routing context. */
function body(request: Request | undefined) {
  if (!request) return undefined;
  return Object.fromEntries(Object.entries(request.payload).filter(([key]) => key !== "__plugin_context"));
}

function button(label: string) {
  return Array.from(document.querySelectorAll<HTMLButtonElement>("button")).find((item) => item.textContent === label);
}

it("saves a new app for the adding role through the plugin and shows a refusal", async () => {
  const requests: Request[] = [];
  let refuse = true;
  const invoke = async ({ method, payload }: Request) => {
    requests.push({ method, payload });
    if (method === "plugin.feishu.accounts.save" && refuse) throw new Error("bad credential");
    const result = method === "plugins.communication.open" ? { generation: "test" }
      : method === "plugin.feishu.accounts.save" ? { account_id: "feishu:feishu:cli_new" } : {};
    return { id: "response", type: "response" as const, method, error: null, payload: result };
  };
  const client = createPluginRpcClient("feishu", invoke);
  let created = "";
  const view = await mountTestComponent(
    <FeishuAccountDetail account={null} roleId="mira" onChanged={(id) => { created = id ?? ""; }} client={client} host={desktopPluginHostServices} />,
    { windowGlobals: { miraDesktop: { invoke, onEvent: () => () => undefined } } },
  );
  try {
    const id = document.querySelector<HTMLInputElement>('input[autocomplete="off"]');
    const secret = document.querySelector<HTMLInputElement>('input[type="password"]');
    assert.ok(id && secret);
    await changeInputValue(id, "cli_new");
    await changeInputValue(secret, "draft-secret");
    await act(async () => button("保存并连接")?.click());
    assert.match(document.body.textContent ?? "", /bad credential/);
    assert.equal(created, "");

    refuse = false;
    await act(async () => button("保存并连接")?.click());
    const saves = requests.filter((item) => item.method === "plugin.feishu.accounts.save");
    assert.deepEqual(body(saves.at(-1)), { role_id: "mira", domain: "feishu", app_id: "cli_new", app_secret: "draft-secret" });
    assert.equal(created, "feishu:feishu:cli_new");
    assert.equal(requests.some((item) => item.method.startsWith("plugin.config.")), false);
  } finally {
    await view.cleanup();
    await client.dispose();
  }
});

it("disconnects an online app through the plugin", async () => {
  const requests: Request[] = [];
  const invoke = async ({ method, payload }: Request) => {
    requests.push({ method, payload });
    const result = method === "plugins.communication.open" ? { generation: "test" }
      : method === "plugin.feishu.accounts.profile" ? { identity: {}, targets: [] } : {};
    return { id: "response", type: "response" as const, method, error: null, payload: result };
  };
  const client = createPluginRpcClient("feishu", invoke);
  const account: AccountSnapshot = {
    id: "feishu:feishu:cli_a", pluginId: "feishu", platform: "feishu", platformAccountId: "feishu:cli_a", configRef: "feishu:cli_a",
    displayName: "A", avatarUrl: "", roleId: "mira", runtimeActive: true,
    connection: "online", capabilities: ["private"], error: "",
    responseRules: { privateEnabled: true, groupEnabled: false, requireMention: false, blockedSenderIds: [], groupRules: [] },
  };
  const view = await mountTestComponent(
    <FeishuAccountDetail account={account} roleId="mira" onChanged={() => undefined} client={client} host={desktopPluginHostServices} />,
    { windowGlobals: { miraDesktop: { invoke, onEvent: () => () => undefined } } },
  );
  try {
    const id = document.querySelector<HTMLInputElement>('input[autocomplete="off"]');
    assert.equal(id?.value, "cli_a");
    await act(async () => button("断开连接")?.click());
    assert.deepEqual(body(requests.find((item) => item.method === "plugin.feishu.accounts.disconnect")),
      { account_id: "feishu:feishu:cli_a", role_id: "mira" });
  } finally {
    await view.cleanup();
    await client.dispose();
  }
});
