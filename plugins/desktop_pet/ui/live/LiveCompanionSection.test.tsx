import assert from "node:assert/strict";
import { test } from "node:test";
import { PluginHostServicesProvider, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import { changeInputValue, createFakeHostServices, createFakePluginClient, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { act } from "react";
import type { LiveConfig } from "./liveContracts";
import { LiveCompanionSection } from "./LiveCompanionSection";
import { useLiveConfig } from "./useLiveConfig";

function Section({ client, petEnabled }: { client: PluginRpcClient; petEnabled: boolean }) {
  const config = useLiveConfig(client, "role");
  return <LiveCompanionSection roleId="role" client={client} config={config} petEnabled={petEnabled} open disabled={false} />;
}

function liveClient(config: LiveConfig, account: Record<string, unknown>) {
  let stored = config;
  return createFakePluginClient({ call: async <T,>(method: string, payload?: Record<string, unknown>) => {
    if (method === "live.config.get") return structuredClone(stored) as T;
    if (method === "live.config.set") { const next = { ...payload }; delete next.role_id; stored = next as LiveConfig; return structuredClone(stored) as T; }
    if (method === "bilibili.account.status") return account as T;
    if (method === "live.status") return { role_id: "role", state: "idle", connection: null, room: null, configured_room_id: stored.room_id, run_id: null, queue_length: 0, generating: false, output_pending: false, connection_error: "", reply_error: "", stop_reason: "", counters: {}, recent: [] } as T;
    throw new Error(`unexpected ${method}`);
  } });
}

test("开始 follows the saved pet switch, the saved room and the login, in that order", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const { host } = createFakeHostServices();
  const client = liveClient({ room_id: null, reply_interval_seconds: 5, wait_timeout_seconds: 30 }, { state: "logged_in", account: { uid: 1, uname: "主播" } });
  const render = (petEnabled: boolean) => <PluginHostServicesProvider services={host}><Section client={client} petEnabled={petEnabled} /></PluginHostServicesProvider>;
  const view = await mountTestComponent(render(false));
  const reason = () => view.container.querySelector('[data-testid="live-start-blocked"]')?.textContent ?? null;
  const start = () => Array.from(view.container.querySelectorAll("button")).find((item) => item.textContent === "开始")!;
  try {
    assert.match(view.container.textContent ?? "", /直播陪伴/);
    assert.equal(reason(), "未启用桌宠");
    await view.render(render(true));
    assert.equal(reason(), "未配置直播间");
    await changeInputValue(view.container.querySelector<HTMLInputElement>('[aria-label="直播间号"]')!, "100");
    assert.equal(reason(), "未配置直播间", "a room not saved yet does not count");
    await act(async () => t.mock.timers.tick(5000));
    assert.equal(reason(), null);
    assert.equal(start().disabled, false);
  } finally { await view.cleanup(); }
});
