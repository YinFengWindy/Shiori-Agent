import assert from "node:assert/strict";
import { it } from "node:test";
import { act } from "react";
import type { AccountSnapshot } from "../../../apps/desktop/renderer/src/accounts/accountClient";
import { createPluginRpcClient, type PluginRpcClient } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";
import { desktopPluginHostServices } from "../../../apps/desktop/renderer/src/plugins/pluginHostServices";
import { changeInputValue, mountTestComponent } from "../../../apps/desktop/renderer/src/shared/testing/domTestHarness";
import { QQBotAccountDetail } from "./QQBotAccountDetail";

function fakeClient(calls: Array<{ method: string; payload: Record<string, unknown> | undefined }>): PluginRpcClient {
  return {
    ...createPluginRpcClient("qqbot"),
    call: async <T,>(method: string, payload?: Record<string, unknown>) => {
      calls.push({ method, payload });
      if (method === "account.detail") return { app_id: "100", has_secret: true, secret_reference: "", connected: true, identity: "QQ 官方机器人应用", bot_id: "bot-id", bot_name: "Bot One" } as T;
      if (method === "account.targets") return { coverage: "observed_c2c_only", targets: [{ chat_id: "c2c:100:opaque-openid", user_openid: "opaque-openid" }] } as T;
      return { account_id: "100" } as T;
    },
  };
}

it("keeps credential edits local until Save and Connect", async () => {
  const calls: Array<{ method: string; payload: Record<string, unknown> | undefined }> = [];
  const changed: string[] = [];
  const view = await mountTestComponent(<QQBotAccountDetail account={null} onChanged={(id) => { if (id) changed.push(id); }} client={fakeClient(calls)} host={desktopPluginHostServices} />);
  try {
    const [appId, secret] = Array.from(view.container.querySelectorAll("input"));
    await changeInputValue(appId, "100");
    await changeInputValue(secret, "draft-secret");
    assert.deepEqual(calls, []);
    const save = Array.from(view.container.querySelectorAll("button")).find((button) => button.textContent === "保存并连接");
    assert.ok(save);
    await act(async () => save.click());
    assert.deepEqual(calls, [{ method: "account.save", payload: { app_id: "100", client_secret: "draft-secret" } }]);
    assert.deepEqual(changed, ["100"]);
  } finally { await view.cleanup(); }
});

it("labels observed C2C targets as application scoped OpenIDs", async () => {
  const calls: Array<{ method: string; payload: Record<string, unknown> | undefined }> = [];
  const account = { id: "100", platformAccountId: "100", displayName: "Bot One" } as AccountSnapshot;
  const view = await mountTestComponent(<QQBotAccountDetail account={account} onChanged={() => undefined} client={fakeClient(calls)} host={desktopPluginHostServices} />);
  try {
    await act(async () => { await Promise.resolve(); });
    assert.match(view.container.textContent, /已交互 C2C 用户/);
    assert.match(view.container.textContent, /仅包含此应用已处理消息的用户 OpenID/);
    assert.match(view.container.textContent, /opaque-openid/);
    assert.doesNotMatch(view.container.textContent, /群聊/);
    assert.deepEqual(calls.map((call) => call.method), ["account.detail", "account.targets"]);
  } finally { await view.cleanup(); }
});
