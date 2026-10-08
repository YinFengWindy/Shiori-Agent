import assert from "node:assert/strict";
import { before, test } from "node:test";
import { act } from "react";
import { PluginHostServicesProvider } from "@yinfengwindy/shiori-sdk";
import { changeInputValue, createFakeHostServices, createFakePluginClient, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import type { RoleVoice } from "../shared/contracts";
let roleSettings: typeof import("./roleSettings");
before(async () => { const view = await mountTestComponent(null); roleSettings = await import("./roleSettings"); await view.cleanup(); });

const voice: RoleVoice = { text_lang: "auto", speed: 1, default: { asset: "a.wav", prompt_text: "", prompt_lang: "zh" }, moods: {} };

async function settle() {
  // Base UI finishes its open/close transition on later frames.
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 50)); });
}

test("the card opens the voice editor from its ⚙ and closing the dialog submits the last edit at once", async () => {
  const { host } = createFakeHostServices();
  const saves: RoleVoice[] = [];
  const client = createFakePluginClient({ call: async <T,>(method: string, payload?: Record<string, unknown>) => {
    if (method === "role.get") return structuredClone(voice) as T;
    if (method === "role.set") { saves.push(payload?.voice as RoleVoice); return payload?.voice as T; }
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
    await settle();
    const dialog = document.querySelector<HTMLElement>('[role="dialog"]')!;
    assert.ok(dialog.querySelector('li[data-reference="开心"]'), "catalog moods reach the editor");
    await act(async () => dialog.querySelector<HTMLButtonElement>('li[data-reference="默认参考"] button[aria-expanded]')!.click());
    await changeInputValue(dialog.querySelector<HTMLTextAreaElement>('[aria-label="默认参考参考转写"]')!, "关闭前的改动");
    assert.equal(saves.length, 0);
    await act(async () => dialog.querySelector<HTMLButtonElement>('button[aria-label="关闭"]')!.click());
    assert.equal(saves.length, 1, "submitted on close, without waiting for the quiet period");
    assert.equal(saves[0].default?.prompt_text, "关闭前的改动");
  } finally { await view.cleanup(); }
});

test("status follows the stored document, neutral before it exists or loads", () => {
  const { roleVoiceStatus } = roleSettings;
  const unset = { ...voice, default: null };
  assert.deepEqual(roleVoiceStatus(null, { saved: null, loadError: "" }), { label: "未保存角色", tone: "off" });
  assert.deepEqual(roleVoiceStatus("role", { saved: null, loadError: "" }), { label: "读取中", tone: "off" });
  assert.deepEqual(roleVoiceStatus("role", { saved: null, loadError: "boom" }), { label: "读取失败", tone: "attention" });
  assert.deepEqual(roleVoiceStatus("role", { saved: unset, loadError: "" }), { label: "未设置默认参考", tone: "off" });
  assert.deepEqual(roleVoiceStatus("role", { saved: voice, loadError: "" }), { label: "已配置", tone: "on" });
});

test("the contribution keeps nothing in the role draft", () => {
  const { gptSoVitsRoleSettings } = roleSettings;
  assert.equal(gptSoVitsRoleSettings.storage, "plugin");
  assert.deepEqual(gptSoVitsRoleSettings.read({ anything: true }), {});
});
