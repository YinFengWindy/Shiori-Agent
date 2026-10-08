import assert from "node:assert/strict";
import { before, test } from "node:test";
import { act } from "react";
import { PluginHostServicesProvider } from "@yinfengwindy/shiori-sdk";
import { createFakeHostServices, createFakePluginClient, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import type { RoleVoice } from "../shared/contracts";
let roleSettings: typeof import("./roleSettings");
before(async () => { const view = await mountTestComponent(null); roleSettings = await import("./roleSettings"); await view.cleanup(); });

const voice: RoleVoice = { text_lang: "auto", speed: 1, default: null, moods: {} };

test("the card shows whether a default reference is set and opens the voice editor from its ⚙", async () => {
  const { host } = createFakeHostServices();
  const client = createFakePluginClient({ call: async <T,>(method: string) => {
    if (method === "role.get") return { ...voice, default: { asset: "a.wav", prompt_text: "", prompt_lang: "zh" } } as T;
    throw new Error(`unexpected ${method}`);
  } });
  const { GptSoVitsRoleCard } = roleSettings;
  const view = await mountTestComponent(<PluginHostServicesProvider services={host}>
    <GptSoVitsRoleCard roleId="role" client={client} moodCatalog={["开心"]} values={{}} onChange={() => assert.fail("no role draft values")} />
  </PluginHostServicesProvider>);
  try {
    assert.match(view.container.textContent ?? "", /GPT-SoVITS 声音已配置/);
    assert.equal(view.container.querySelector('[role="switch"], input[type="checkbox"]'), null, "the card has no switch");
    await act(async () => view.container.querySelector<HTMLButtonElement>('button[aria-label="GPT-SoVITS 声音设置"]')!.click());
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 50)); });
    const dialog = document.querySelector<HTMLElement>('[role="dialog"]')!;
    assert.ok(dialog.querySelector('li[data-reference="默认参考"]'));
    assert.ok(dialog.querySelector('li[data-reference="开心"]'));
  } finally { await view.cleanup(); }
});

test("status reflects a missing default reference and a failed read", () => {
  const { roleVoiceStatus } = roleSettings;
  assert.deepEqual(roleVoiceStatus({ draft: voice, loadError: "" }), { label: "未设置默认参考", tone: "off" });
  assert.deepEqual(roleVoiceStatus({ draft: null, loadError: "boom" }), { label: "读取失败", tone: "attention" });
});

test("the contribution keeps nothing in the role draft", () => {
  const { gptSoVitsRoleSettings } = roleSettings;
  assert.equal(gptSoVitsRoleSettings.storage, "plugin");
  assert.deepEqual(gptSoVitsRoleSettings.read({ anything: true }), {});
});
