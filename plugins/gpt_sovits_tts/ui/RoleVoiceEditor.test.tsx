import assert from "node:assert/strict";
import { before, test } from "node:test";
import { act } from "react";
import { PluginHostServicesProvider } from "@yinfengwindy/shiori-sdk";
import { changeInputValue, createFakeHostServices, createFakePluginClient, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import type { RoleVoice } from "../shared/contracts";
let RoleVoiceEditor: typeof import("./RoleVoiceEditor").RoleVoiceEditor;
before(async () => { const view = await mountTestComponent(null); ({ RoleVoiceEditor } = await import("./RoleVoiceEditor")); await view.cleanup(); });

const voice: RoleVoice = { text_lang: "auto", speed: 1, default: { asset: "default.wav", prompt_text: "平静参考", prompt_lang: "zh" }, moods: {
  开心: { asset: "happy.wav", prompt_text: "开心参考", prompt_lang: "zh" }, 难过: { asset: "sad.wav", prompt_text: "难过参考", prompt_lang: "zh" },
} };

test("private role save preserves multiple mood references and keeps dirty edits when persistence fails", async () => {
  const { host, calls } = createFakeHostServices(); const requests: Array<{ method: string; payload?: Record<string, unknown> }> = []; const dirty: boolean[] = [];
  let failed = true;
  const client = createFakePluginClient({ call: async <T,>(method: string, payload?: Record<string, unknown>) => {
    requests.push({ method, payload });
    if (method === "role.set") { if (failed) throw new Error("private write failed"); return payload?.voice as T; }
    return voice as T;
  } });
  const view = await mountTestComponent(<PluginHostServicesProvider services={host}><RoleVoiceEditor roleId="role" role={{ id: "role", name: "Role", moodCatalog: ["开心", "难过", "生气"] }} client={client} disabled={false} onDirtyChange={(value) => dirty.push(value)} /></PluginHostServicesProvider>);
  try {
    assert.deepEqual(Array.from(view.container.querySelectorAll("legend"), (item) => item.textContent), ["默认参考", "开心", "难过", "生气"]);
    const transcript = view.container.querySelector<HTMLTextAreaElement>('[aria-label="默认参考参考转写"]')!;
    await changeInputValue(transcript, "编辑后的参考转写");
    const save = Array.from(view.container.querySelectorAll("button")).find((button) => button.textContent === "保存声音设置")!;
    await act(async () => save.click());
    assert.equal(transcript.value, "编辑后的参考转写"); assert.equal(dirty.at(-1), true); assert.equal(save.disabled, false);
    assert.match(view.container.textContent ?? "", /private write failed/);
    failed = false; await act(async () => save.click());
    assert.equal(dirty.at(-1), false);
    assert.deepEqual(requests.at(-1), { method: "role.set", payload: { role_id: "role", voice: { ...voice, default: { ...voice.default, prompt_text: "编辑后的参考转写" } } } });
    assert.equal(requests.some((request) => request.method === "roles.update"), false);
    assert.equal(calls.some((call) => call.service === "config.save"), false);
  } finally { await view.cleanup(); }
});

test("a missing role or failed private read exposes no saveable default voice", async () => {
  const { host } = createFakeHostServices(); const requests: string[] = [];
  const client = createFakePluginClient({ call: async (method) => { requests.push(method); throw new Error("private read failed"); } });
  const render = (roleId: string | null) => <PluginHostServicesProvider services={host}><RoleVoiceEditor roleId={roleId} role={roleId ? { id: roleId, name: "Role", moodCatalog: [] } : null} client={client} disabled={false} onDirtyChange={() => {}} /></PluginHostServicesProvider>;
  const view = await mountTestComponent(render(null));
  try {
    assert.match(view.container.textContent ?? "", /请先保存角色/); assert.deepEqual(requests, []);
    await view.render(render("role"));
    assert.match(view.container.textContent ?? "", /private read failed/);
    assert.equal(view.container.querySelector("input"), null); assert.equal(view.container.querySelector("button"), null);
  } finally { await view.cleanup(); }
});
