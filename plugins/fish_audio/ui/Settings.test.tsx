import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { changeInputValue, createFakeHostServices, createFakePluginClient, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { FishSettingsPage } from "./Settings";

function button(container: HTMLElement, label: string) {
  const found = Array.from(container.querySelectorAll("button")).find((item) => item.textContent === label);
  assert.ok(found, `missing button: ${label}`);
  return found;
}

test("an invalid key stays editable and correcting it saves without trapping autosave in retry", async () => {
  const { host } = createFakeHostServices();
  const saves: Array<Record<string, unknown> | undefined> = [];
  let storedKey = "";
  const client = createFakePluginClient({ call: async <T,>(method: string, payload?: Record<string, unknown>) => {
    if (method === "settings.get") return { has_api_key: false, tts_model: "s2.1-pro-free" } as T;
    assert.equal(method, "settings.set", "global settings never read or write a role voice");
    saves.push(payload);
    const key = String(payload?.api_key);
    if (!/^[ -~]+$/.test(key)) throw new Error("API Key 格式无效");
    storedKey = key;
    return { has_api_key: true, tts_model: payload?.tts_model } as T;
  } });
  const view = await mountTestComponent(<FishSettingsPage client={client} host={host} subsectionId="fish_audio" onSelectSubsection={() => {}} />);
  try {
    const input = view.container.querySelector<HTMLInputElement>('input[type="password"]')!;
    await changeInputValue(input, "错误-secret");
    await act(async () => button(view.container, "保存 Key").click());
    assert.deepEqual(saves, [], "invalid local text never enters the failed-write queue");
    assert.equal(input.value, "错误-secret");
    assert.equal(input.getAttribute("aria-invalid"), "true");
    assert.match(view.container.textContent ?? "", /ASCII/);
    assert.doesNotMatch(view.container.textContent ?? "", /错误-secret/);

    await changeInputValue(input, "  valid-key  ");
    await act(async () => button(view.container, "保存 Key").click());
    assert.equal(storedKey, "valid-key");
    assert.deepEqual(saves, [{ tts_model: "s2.1-pro-free", api_key: "valid-key", clear_api_key: false }]);
    assert.equal(input.value, "");
    assert.equal(input.hasAttribute("aria-invalid"), false);
    assert.doesNotMatch(view.container.textContent ?? "", /ASCII|重试/);
    assert.equal(view.container.querySelector('[aria-label="Fish Audio 声音 ID"]'), null);
  } finally { await view.cleanup(); }
});

test("a valid key survives transient persistence failure and retries with its selected model", async () => {
  const { host } = createFakeHostServices();
  const saves: Array<Record<string, unknown> | undefined> = [];
  let fail = true;
  let storedKey = "";
  const client = createFakePluginClient({ call: async <T,>(method: string, payload?: Record<string, unknown>) => {
    if (method === "settings.get") return { has_api_key: false, tts_model: "s2-pro" } as T;
    assert.equal(method, "settings.set");
    saves.push(payload);
    if (fail) throw new Error("暂时无法保存设置");
    storedKey = String(payload?.api_key);
    return { has_api_key: true, tts_model: payload?.tts_model } as T;
  } });
  const view = await mountTestComponent(<FishSettingsPage client={client} host={host} subsectionId="fish_audio" onSelectSubsection={() => {}} />);
  try {
    const input = view.container.querySelector<HTMLInputElement>('input[type="password"]')!;
    await changeInputValue(input, "valid-key");
    await act(async () => button(view.container, "保存 Key").click());
    assert.equal(storedKey, "");
    assert.match(view.container.textContent ?? "", /暂时无法保存设置/);
    assert.doesNotMatch(view.container.textContent ?? "", /valid-key/);
    fail = false;
    await act(async () => button(view.container, "重试").click());
    assert.equal(storedKey, "valid-key");
    assert.deepEqual(saves, [
      { tts_model: "s2-pro", api_key: "valid-key", clear_api_key: false },
      { tts_model: "s2-pro", api_key: "valid-key", clear_api_key: false },
    ]);
    assert.doesNotMatch(view.container.textContent ?? "", /暂时无法保存设置|重试/);
    assert.equal(input.value, "");
  } finally { await view.cleanup(); }
});
