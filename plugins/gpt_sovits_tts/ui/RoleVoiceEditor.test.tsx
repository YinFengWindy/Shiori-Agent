import assert from "node:assert/strict";
import { before, test } from "node:test";
import { act } from "react";
import { PluginHostServicesProvider } from "@yinfengwindy/shiori-sdk";
import { changeInputValue, chooseSelectOption, createFakeHostServices, createFakePluginClient, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
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
    assert.deepEqual(Array.from(view.container.querySelectorAll("legend"), (item) => item.textContent), ["默认参考", "开心", "难过"]);
    assert.ok(Array.from(view.container.querySelectorAll("button")).some((button) => button.textContent === "生气"));
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

test("an empty host catalog supports private moods, failed saves, removal and preview without host writes", async () => {
  const { host, calls } = createFakeHostServices({ pickFiles: async () => ["picked.wav"] });
  const requests: Array<{ method: string; payload?: Record<string, unknown> }> = [];
  const dirty: boolean[] = [];
  let asset = 0; let rejectSave = true;
  const client = createFakePluginClient({
    call: async <T,>(method: string, payload?: Record<string, unknown>) => {
      requests.push({ method, payload });
      if (method === "reference.import") return { asset: `${++asset}.wav`, duration: 3.2 } as T;
      if (method === "role.set") { if (rejectSave) throw new Error("cannot save private voice"); return payload?.voice as T; }
      return { ...voice, moods: {} } as T;
    },
    services: { list: async () => ({ services: [] }), call: async <T,>(_service: unknown, method: string, payload?: Record<string, unknown>) => { requests.push({ method, payload }); return { audio_base64: "audio", format: "wav" } as T; } },
    background: { call: async <T,>(_name: string, payload?: Record<string, unknown>) => ({ id: payload?.id, role_id: "one", phase: "idle", error: "" }) as T },
  });
  const render = (roleId: string) => <PluginHostServicesProvider services={host}><RoleVoiceEditor roleId={roleId} role={{ id: roleId, name: roleId, moodCatalog: [] }} client={client} disabled={false} onDirtyChange={(value) => dirty.push(value)} /></PluginHostServicesProvider>;
  const view = await mountTestComponent(render("one"));
  const button = (label: string) => Array.from(view.container.querySelectorAll("button")).find((item) => item.textContent === label)!;
  try {
    for (const mood of ["happy", "sad"]) {
      await changeInputValue(view.container.querySelector('[aria-label="情绪名称"]')!, mood);
      await act(async () => button("添加情绪").click());
      assert.equal(dirty.at(-1), true);
      assert.equal(button("保存声音设置").disabled, true, "an unimported name cannot be silently lost on save");
      const field = Array.from(view.container.querySelectorAll("fieldset")).find((item) => item.querySelector("legend")?.textContent === mood)!;
      await act(async () => field.querySelector("button")!.click());
      await changeInputValue(field.querySelector("textarea")!, `${mood} reference`);
    }
    await act(async () => button("保存声音设置").click());
    assert.match(view.container.textContent ?? "", /cannot save private voice/);
    assert.equal(dirty.at(-1), true);
    rejectSave = false;
    await act(async () => button("保存声音设置").click());
    assert.equal(dirty.at(-1), false);
    const saved = requests.filter((item) => item.method === "role.set").at(-1)?.payload?.voice;
    assert.deepEqual(saved, { ...voice, moods: { happy: { asset: "1.wav", prompt_text: "happy reference", prompt_lang: "zh" }, sad: { asset: "2.wav", prompt_text: "sad reference", prompt_lang: "zh" } } });
    await chooseSelectOption("试听情绪", "sad");
    await act(async () => button("试听").click());
    assert.equal(requests.find((item) => item.method === "synthesize")?.payload?.mood, "sad");
    await act(async () => view.container.querySelector<HTMLButtonElement>('[aria-label="删除情绪 sad"]')!.click());
    assert.equal(dirty.at(-1), true);
    assert.equal(view.container.querySelector('[aria-label="sad参考转写"]'), null);
    await act(async () => button("保存声音设置").click());
    assert.deepEqual(requests.filter((item) => item.method === "role.set").at(-1)?.payload?.voice, { ...voice, moods: { happy: { asset: "1.wav", prompt_text: "happy reference", prompt_lang: "zh" } } });
    await changeInputValue(view.container.querySelector('[aria-label="情绪名称"]')!, "pending");
    await act(async () => button("添加情绪").click());
    assert.equal(dirty.at(-1), true);
    await view.render(render("two"));
    assert.equal(dirty.at(-1), false);
    assert.equal(view.container.querySelector('[aria-label="happy参考转写"]'), null);
    assert.equal(Array.from(view.container.querySelectorAll("legend")).some((item) => item.textContent === "pending"), false);
    assert.equal(requests.some((item) => item.method === "roles.update"), false);
    assert.equal(calls.some((item) => item.service === "config.save"), false);
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
