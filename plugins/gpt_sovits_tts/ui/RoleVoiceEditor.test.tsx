import assert from "node:assert/strict";
import { before, test } from "node:test";
import { act } from "react";
import { PluginHostServicesProvider, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import { changeInputValue, createFakeHostServices, createFakePluginClient, deferred, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import type { RoleVoice } from "../shared/contracts";
let RoleVoiceEditor: typeof import("./RoleVoiceEditor").RoleVoiceEditor;
let useRoleVoice: typeof import("./useRoleVoice").useRoleVoice;
before(async () => {
  const view = await mountTestComponent(null);
  ({ RoleVoiceEditor } = await import("./RoleVoiceEditor"));
  ({ useRoleVoice } = await import("./useRoleVoice"));
  await view.cleanup();
});

const voice: RoleVoice = { text_lang: "auto", speed: 1, default: { asset: "default.wav", prompt_text: "平静参考", prompt_lang: "zh", duration: 4.2 }, moods: {
  开心: { asset: "happy.wav", prompt_text: "开心参考", prompt_lang: "zh", duration: 3.5 },
} };

type Request = { method: string; payload?: Record<string, unknown> };

/** A client whose role.set the test controls; every RPC and service call lands in `requests`. */
function voiceClient(requests: Request[], save: (voice: RoleVoice) => Promise<RoleVoice>) {
  return createFakePluginClient({
    call: async <T,>(method: string, payload?: Record<string, unknown>) => {
      requests.push({ method, payload });
      if (method === "role.set") return await save(payload?.voice as RoleVoice) as T;
      return structuredClone(voice) as T;
    },
    services: { list: async () => ({ services: [] }), call: async <T,>(_service: unknown, method: string, payload?: Record<string, unknown>) => { requests.push({ method, payload }); return { audio_base64: "audio", format: "wav" } as T; } },
    background: { call: async <T,>(_name: string, payload?: Record<string, unknown>) => ({ id: payload?.id, role_id: "role", phase: "idle", error: "" }) as T },
  });
}

/** The card's wiring: the autosaved document and its dialog body. */
function Editor({ roleId, client }: { roleId: string | null; client: PluginRpcClient }) {
  const state = useRoleVoice(client, roleId);
  return <RoleVoiceEditor roleId={roleId} client={client} voice={state} moodCatalog={[]} disabled={false} />;
}

async function mount(client: PluginRpcClient) {
  const fake = createFakeHostServices();
  const render = (roleId: string | null) => <PluginHostServicesProvider services={fake.host}><Editor roleId={roleId} client={client} /></PluginHostServicesProvider>;
  const view = await mountTestComponent(render("role"));
  const button = (label: string) => Array.from(view.container.querySelectorAll("button")).find((item) => item.textContent === label || item.getAttribute("aria-label") === label);
  const transcript = async (title: string, text: string) => {
    if (!view.container.querySelector(`[aria-label="${title}参考转写"]`)) await act(async () => view.container.querySelector<HTMLButtonElement>(`li[data-reference="${title}"] button[aria-expanded]`)!.click());
    await changeInputValue(view.container.querySelector<HTMLTextAreaElement>(`[aria-label="${title}参考转写"]`)!, text);
  };
  return { ...fake, view, button, transcript, render };
}

const saves = (requests: Request[]) => requests.filter((item) => item.method === "role.set").map((item) => item.payload?.voice);

test("edits autosave once typing pauses; a failed save keeps the draft until retry, with no save button", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const requests: Request[] = []; let fail = true;
  const ui = await mount(voiceClient(requests, async (next) => { if (fail) throw new Error("private write failed"); return next; }));
  try {
    assert.equal(ui.button("保存声音设置"), undefined);
    await ui.transcript("默认参考", "编辑");
    await act(async () => t.mock.timers.tick(200));
    await ui.transcript("默认参考", "编辑后的参考转写");
    await act(async () => t.mock.timers.tick(399));
    assert.deepEqual(saves(requests), []);
    await act(async () => t.mock.timers.tick(1));
    const edited = { ...voice, default: { ...voice.default!, prompt_text: "编辑后的参考转写" } };
    assert.deepEqual(saves(requests), [edited], "two edits inside the quiet period merge into one save");
    assert.match(ui.view.container.textContent ?? "", /private write failed/);
    assert.equal(ui.view.container.querySelector<HTMLTextAreaElement>('[aria-label="默认参考参考转写"]')!.value, "编辑后的参考转写");
    assert.equal(ui.uiRenders.SettingsSavedStatus.at(-1)?.phase, "error");

    fail = false;
    await act(async () => ui.button("重试")!.click());
    assert.deepEqual(saves(requests), [edited, edited]);
    assert.equal(ui.uiRenders.SettingsSavedStatus.at(-1)?.phase, "idle");
    assert.equal(requests.some((item) => item.method === "roles.update"), false);
  } finally { await ui.view.cleanup(); }
});

test("leaving the role submits the last edit at once", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const requests: Request[] = [];
  const ui = await mount(voiceClient(requests, async (next) => next));
  try {
    await ui.transcript("开心", "最后一次改动");
    await ui.view.render(ui.render("other"));
    assert.deepEqual(requests.filter((item) => item.method === "role.set").map((item) => item.payload?.role_id), ["role"]);
    assert.equal((saves(requests)[0] as RoleVoice).moods.开心.prompt_text, "最后一次改动");
  } finally { await ui.view.cleanup(); }
});

test("a row's preview with a pending edit plays the stored latest voice; a failed save disables it", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const requests: Request[] = []; let write = deferred<RoleVoice>();
  const ui = await mount(voiceClient(requests, () => write.promise));
  try {
    await ui.transcript("开心", "新的开心参考");
    await act(async () => ui.button("试听开心")!.click());
    assert.equal(requests.some((item) => item.method === "synthesize"), false);
    await act(async () => write.resolve(saves(requests)[0] as RoleVoice));
    const synthesize = requests.findIndex((item) => item.method === "synthesize");
    assert.ok(synthesize > requests.findIndex((item) => item.method === "role.set"));
    assert.equal(requests[synthesize].payload?.mood, "开心");

    write = deferred<RoleVoice>();
    await ui.transcript("开心", "再次修改");
    await act(async () => ui.button("试听默认参考")!.click());
    await act(async () => write.reject(new Error("disk full")));
    assert.equal(ui.button("试听默认参考")!.disabled, true);
    assert.match(ui.view.container.textContent ?? "", /保存失败，暂不能试听/);
  } finally { await ui.view.cleanup(); }
});

test("a role not yet saved or a failed read exposes no editable voice", async () => {
  const requests: string[] = [];
  const ui = await mount(createFakePluginClient({ call: async (method) => { requests.push(method); throw new Error("private read failed"); } }));
  try {
    await ui.view.render(ui.render(null));
    assert.match(ui.view.container.textContent ?? "", /请先保存角色/);
    await ui.view.render(ui.render("role"));
    assert.match(ui.view.container.textContent ?? "", /private read failed/);
    assert.equal(ui.view.container.querySelector("li"), null);
    assert.ok(ui.button("重新加载"));
  } finally { await ui.view.cleanup(); }
});
