import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { changeInputValue, createFakeHostServices, createFakePluginClient, deferred, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { GptSoVitsSettingsPage } from "./Settings";
import type { GptSoVitsHealth, GptSoVitsSettings } from "../shared/contracts";

const settings = { connection_mode: "external", url: "http://127.0.0.1:9880", version: "v2ProPlus", gpt_weights: "voice.ckpt", sovits_weights: "voice.pth" } satisfies GptSoVitsSettings;
const health = (recovery_required: boolean) => ({ reachable: true, configured_version: "v2ProPlus", model_verified: false, busy: false, recovery_required, instance: null }) satisfies GptSoVitsHealth;

function buttons(container: HTMLElement) {
  return (label: string) => Array.from(container.querySelectorAll("button")).find((item) => item.textContent === label);
}

test("recovery requires explicit restart confirmation and connection status never claims a verified model", async () => {
  const { host, uiRenders } = createFakeHostServices();
  const requests: Array<{ method: string; payload?: Record<string, unknown> }> = [];
  const client = createFakePluginClient({ call: async <T,>(method: string, payload?: Record<string, unknown>) => {
    requests.push({ method, payload });
    if (method === "settings.get") return settings as T;
    if (method === "settings.set") return payload as T;
    return { ...health(true), instance: { operation: "previous", url: settings.url, state: "unknown" } } as T;
  } });
  const view = await mountTestComponent(<GptSoVitsSettingsPage client={client} host={host} subsectionId="gpt_sovits_tts" onSelectSubsection={() => {}} />);
  const button = (label: string) => buttons(view.container)(label)!;
  try {
    await act(async () => button("检查连接").click());
    assert.match(view.container.textContent ?? "", /模型身份未验证/);
    assert.equal(requests.some((request) => request.method === "reconnect"), false);
    await act(async () => button("我已重启服务").click());
    assert.equal(requests.some((request) => request.method === "reconnect"), false);
    assert.equal(uiRenders.ConfirmDialog.at(-1)?.persona, true);
    await act(async () => button("取消").click());
    assert.equal(requests.some((request) => request.method === "reconnect"), false);
    await act(async () => button("我已重启服务").click());
    await act(async () => button("确认已重启").click());
    assert.deepEqual(requests.slice(-2), [{ method: "reconnect", payload: { service_restarted: true } }, { method: "health", payload: undefined }]);
    await changeInputValue(view.container.querySelector<HTMLInputElement>('[aria-label="服务地址"]')!, "http://localhost:9881");
    assert.equal(button("我已重启服务").disabled, true);
  } finally { await view.cleanup(); }
});

test("edits autosave after the quiet period, actions wait for the save, and a stored change clears stale health", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const { host, uiRenders } = createFakeHostServices();
  const saves: Array<Record<string, unknown> | undefined> = []; const write = deferred<GptSoVitsSettings>();
  const client = createFakePluginClient({ call: async <T,>(method: string, payload?: Record<string, unknown>) => {
    if (method === "settings.get") return settings as T;
    if (method === "settings.set") { saves.push(payload); return write.promise as Promise<T>; }
    return health(false) as T;
  } });
  const view = await mountTestComponent(<GptSoVitsSettingsPage client={client} host={host} subsectionId="gpt_sovits_tts" onSelectSubsection={() => {}} />);
  const button = buttons(view.container);
  try {
    assert.equal(button("保存"), undefined);
    await act(async () => button("检查连接")!.click());
    assert.match(view.container.textContent ?? "", /服务可达/);

    await changeInputValue(view.container.querySelector<HTMLInputElement>('[aria-label="GPT 权重路径"]')!, "other.ckpt");
    assert.equal(button("检查连接")!.disabled, true, "a pending edit counts as saving");
    await act(async () => t.mock.timers.tick(399));
    assert.deepEqual(saves, []);
    await act(async () => t.mock.timers.tick(1));
    assert.deepEqual(saves, [{ ...settings, gpt_weights: "other.ckpt" }]);
    assert.equal(button("检查连接")!.disabled, true);
    assert.equal(uiRenders.SettingsSavedStatus.at(-1)?.phase, "saving");

    await act(async () => write.resolve({ ...settings, gpt_weights: "other.ckpt" }));
    assert.equal(uiRenders.SettingsSavedStatus.at(-1)?.phase, "idle");
    assert.equal(button("检查连接")!.disabled, false);
    assert.doesNotMatch(view.container.textContent ?? "", /服务可达/, "health of the previous settings is dropped");
  } finally { await view.cleanup(); }
});

test("a failed save keeps the edit and disables actions until retry; a failed read offers reload", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const { host } = createFakeHostServices();
  let failSave = true; let failLoad = true; const saves: unknown[] = [];
  const client = createFakePluginClient({ call: async <T,>(method: string, payload?: Record<string, unknown>) => {
    if (method === "settings.get") { if (failLoad) throw new Error("settings unreadable"); return settings as T; }
    if (method === "settings.set") { saves.push(payload); if (failSave) throw new Error("invalid loopback URL"); return payload as T; }
    return health(false) as T;
  } });
  const view = await mountTestComponent(<GptSoVitsSettingsPage client={client} host={host} subsectionId="gpt_sovits_tts" onSelectSubsection={() => {}} />);
  const button = buttons(view.container);
  try {
    assert.match(view.container.textContent ?? "", /settings unreadable/);
    assert.equal(view.container.querySelector("input"), null);
    failLoad = false;
    await act(async () => button("重新加载")!.click());
    assert.equal(button("重新加载"), undefined);

    const url = view.container.querySelector<HTMLInputElement>('[aria-label="服务地址"]')!;
    await changeInputValue(url, "https://remote.invalid");
    await act(async () => t.mock.timers.tick(400));
    assert.match(view.container.textContent ?? "", /invalid loopback URL/);
    assert.equal(url.value, "https://remote.invalid");
    assert.equal(button("检查连接")!.disabled, true);

    failSave = false;
    await act(async () => button("重试")!.click());
    assert.deepEqual(saves, [{ ...settings, url: "https://remote.invalid" }, { ...settings, url: "https://remote.invalid" }]);
    assert.equal(button("重试"), undefined);
    assert.equal(button("检查连接")!.disabled, false);
  } finally { await view.cleanup(); }
});
