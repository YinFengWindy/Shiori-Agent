import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { changeInputValue, createFakeHostServices, createFakePluginClient, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { GptSoVitsSettingsPage } from "./Settings";
import type { GptSoVitsHealth, GptSoVitsSettings } from "../shared/contracts";

test("recovery requires explicit restart confirmation and connection status never claims a verified model", async () => {
  const { host, uiRenders } = createFakeHostServices();
  const requests: Array<{ method: string; payload?: Record<string, unknown> }> = [];
  const client = createFakePluginClient({ call: async <T,>(method: string, payload?: Record<string, unknown>) => {
    requests.push({ method, payload });
    const settings = { url: "http://127.0.0.1:9880", version: "v2ProPlus", gpt_weights: "voice.ckpt", sovits_weights: "voice.pth" } satisfies GptSoVitsSettings;
    const health = { reachable: true, configured_version: "v2ProPlus", model_verified: false, busy: false, recovery_required: true, instance: { operation: "previous", url: settings.url, state: "unknown" } } satisfies GptSoVitsHealth;
    return (method === "settings.get" ? settings : health) as T;
  } });
  const view = await mountTestComponent(<GptSoVitsSettingsPage client={client} host={host} subsectionId="gpt_sovits_tts" onSelectSubsection={() => {}} />);
  const button = (label: string) => Array.from(view.container.querySelectorAll("button")).find((item) => item.textContent === label)!;
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
