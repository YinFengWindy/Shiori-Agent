import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { PluginHostServicesProvider, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import { changeInputValue, createFakeHostServices, createFakePluginClient, deferred, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import type { LiveConfig } from "./liveContracts";
import { LiveCompanionSection } from "./LiveCompanionSection";
import { useLiveConfig } from "./useLiveConfig";

function Section({ client, petEnabled, open }: { client: PluginRpcClient; petEnabled: boolean; open: boolean }) {
  const config = useLiveConfig(client, "role");
  return <LiveCompanionSection roleId="role" client={client} config={config} petEnabled={petEnabled} open={open} disabled={false} />;
}

const idle = { role_id: "role", state: "idle", connection: null, room: null, configured_room_id: null, run_id: null, queue_length: 0, generating: false, output_pending: false, connection_error: "", reply_error: "", stop_reason: "", counters: {}, recent: [] };

/** The section's backend; `speech` and `configLoad` are switched by the test. */
function liveClient() {
  let stored: LiveConfig = { room_id: null, reply_interval_seconds: 5, wait_timeout_seconds: 30 };
  const control = { speech: { enabled: false, tts: null as unknown }, configLoad: null as Promise<void> | null, voiceReads: 0 };
  const client = createFakePluginClient({ call: async <T,>(method: string, payload?: Record<string, unknown>) => {
    if (method === "live.config.get") { if (control.configLoad) await control.configLoad; return structuredClone(stored) as T; }
    if (method === "live.config.set") { const next = { ...payload }; delete next.role_id; stored = next as LiveConfig; return structuredClone(stored) as T; }
    if (method === "voice.preferences.get") { control.voiceReads += 1; return { hotkey: "", microphone_device_id: "", asr: null, ...control.speech } as T; }
    if (method === "bilibili.account.status") return { state: "logged_in", account: { uid: 1, uname: "主播" } } as T;
    if (method === "live.status") return idle as T;
    throw new Error(`unexpected ${method}`);
  } });
  return { client, control };
}

async function mountSection(client: PluginRpcClient, petEnabled: boolean) {
  const { host } = createFakeHostServices();
  const render = (enabled: boolean, open = true) => <PluginHostServicesProvider services={host}><Section client={client} petEnabled={enabled} open={open} /></PluginHostServicesProvider>;
  const view = await mountTestComponent(render(petEnabled));
  const reason = () => view.container.querySelector('[data-testid="live-start-blocked"]')?.textContent ?? null;
  const start = () => Array.from(view.container.querySelectorAll("button")).find((item) => item.textContent === "开始")!;
  return { view, render, reason, start };
}

test("开始 follows the saved pet switch, the saved room, TTS and the login, in the backend gate's order", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const { client, control } = liveClient();
  const ui = await mountSection(client, false);
  try {
    assert.match(ui.view.container.textContent ?? "", /直播陪伴/);
    assert.equal(ui.reason(), "未启用桌宠");
    await ui.view.render(ui.render(true));
    assert.equal(ui.reason(), "未配置直播间");
    await changeInputValue(ui.view.container.querySelector<HTMLInputElement>('[aria-label="直播间号"]')!, "100");
    assert.equal(ui.reason(), "未配置直播间", "a room not saved yet does not count");
    await act(async () => t.mock.timers.tick(5000));
    assert.equal(ui.reason(), "未开启桌宠语音");

    // TTS is set on the settings page; reopening the dialog reads it again.
    control.speech = { enabled: true, tts: { plugin_id: "tts", service_id: "say" } };
    await ui.view.render(ui.render(true, false));
    await ui.view.render(ui.render(true, true));
    assert.equal(control.voiceReads, 2);
    assert.equal(ui.reason(), null);
    assert.equal(ui.start().disabled, false);
  } finally { await ui.view.cleanup(); }
});

test("settings still loading block 开始 without claiming there is no room", async () => {
  const { client, control } = liveClient();
  const load = deferred<void>();
  control.configLoad = load.promise;
  const ui = await mountSection(client, true);
  try {
    assert.equal(ui.reason(), null, "no reason shown while the room is unknown");
    assert.equal(ui.view.container.querySelector('[data-testid="live-start-blocked"]'), null);
    assert.equal(ui.start().disabled, true);
    assert.match(ui.view.container.textContent ?? "", /读取中…/);
    await act(async () => load.resolve());
    assert.equal(ui.reason(), "未配置直播间");
  } finally { await ui.view.cleanup(); }
});
