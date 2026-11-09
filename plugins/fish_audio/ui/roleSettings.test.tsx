import assert from "node:assert/strict";
import { before, test } from "node:test";
import { act } from "react";
import { PluginHostServicesProvider, type TtsResult } from "@yinfengwindy/shiori-sdk";
import { changeInputValue, chooseSelectOption, createFakeHostServices, createFakePluginClient, deferred, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import type { RoleVoice } from "../shared/contracts";
let roleSettings: typeof import("./roleSettings");
before(async () => { const view = await mountTestComponent(null); roleSettings = await import("./roleSettings"); await view.cleanup(); });
const settle = () => act(async () => { await new Promise((resolve) => setTimeout(resolve, 50)); });

test("role details persist voice and language separately for each role and never show API Key", async () => {
  const { host } = createFakeHostServices();
  const voices: Record<string, RoleVoice> = { alice: { reference_id: "alice-voice", speed: 1, language: "auto" }, bob: { reference_id: "bob-voice", speed: 0.8, language: "en" } };
  const client = createFakePluginClient({ call: async <T,>(method: string, payload?: Record<string, unknown>) => {
    const id = String(payload?.role_id);
    if (method === "role.get") return structuredClone(voices[id]) as T;
    if (method === "role.set") { voices[id] = structuredClone(payload?.voice as RoleVoice); return voices[id] as T; }
    throw new Error(method);
  } });
  const { FishRoleCard } = roleSettings;
  const content = (id: string) => <PluginHostServicesProvider services={host}><FishRoleCard roleId={id} client={client} moodCatalog={[]} values={{}} onChange={() => assert.fail("must not write role draft")} /></PluginHostServicesProvider>;
  const view = await mountTestComponent(content("alice"));
  try {
    await act(async () => view.container.querySelector<HTMLButtonElement>('button[aria-label="Fish Audio 声音设置"]')!.click());
    await settle();
    const dialog = document.querySelector<HTMLElement>('[role="dialog"]')!;
    assert.equal(dialog.querySelector('input[type="password"]'), null);
    await changeInputValue(dialog.querySelector<HTMLInputElement>('[aria-label="Fish Audio 声音 ID"]')!, "new-alice");
    await chooseSelectOption("Fish Audio 文本语言", "日语");
    await act(async () => dialog.querySelector<HTMLButtonElement>('button[aria-label="关闭"]')!.click());
    assert.equal(voices.alice.reference_id, "new-alice");
    assert.equal(voices.alice.language, "ja");
    assert.equal(voices.bob.reference_id, "bob-voice");
    assert.equal(voices.bob.language, "en");
    await view.render(content("bob"));
    await act(async () => view.container.querySelector<HTMLButtonElement>('button[aria-label="Fish Audio 声音设置"]')!.click());
    await settle();
    assert.equal(document.querySelector<HTMLInputElement>('[aria-label="Fish Audio 声音 ID"]')?.value, "bob-voice");
    assert.equal(document.querySelector('[aria-label="Fish Audio 文本语言"]')?.textContent, "英语");
    await act(async () => document.querySelector<HTMLButtonElement>('button[aria-label="关闭"]')!.click());
    await view.render(content("alice"));
    await act(async () => view.container.querySelector<HTMLButtonElement>('button[aria-label="Fish Audio 声音设置"]')!.click());
    await settle();
    assert.equal(document.querySelector('[aria-label="Fish Audio 文本语言"]')?.textContent, "日语");
    await chooseSelectOption("Fish Audio 文本语言", "自动识别");
    assert.equal(voices.alice.language, "auto");
    assert.equal(voices.bob.language, "en");
  } finally { await view.cleanup(); }
});

test("closing the retained capability dialog retires pending synthesis before its audio arrives", async () => {
  const { host } = createFakeHostServices();
  const synthesis = deferred<TtsResult>();
  const commands: string[] = [];
  const client = createFakePluginClient({
    call: async <T,>() => ({ reference_id: "alice", speed: 1, language: "auto" }) as T,
    services: { list: async () => ({ services: [] }), call: async <T,>() => await synthesis.promise as T },
    background: { call: async <T,>(method: string) => { commands.push(method); return { id: "", phase: "idle", error: "" } as T; } },
  });
  const { FishRoleCard } = roleSettings;
  const view = await mountTestComponent(<PluginHostServicesProvider services={host}><FishRoleCard roleId="alice" client={client} moodCatalog={[]} values={{}} onChange={() => {}} /></PluginHostServicesProvider>);
  try {
    await act(async () => view.container.querySelector<HTMLButtonElement>('button[aria-label="Fish Audio 声音设置"]')!.click());
    await settle();
    const dialog = document.querySelector<HTMLElement>('[role="dialog"]')!;
    await act(async () => Array.from(dialog.querySelectorAll("button")).find((button) => button.textContent === "试听")!.click());
    await act(async () => dialog.querySelector<HTMLButtonElement>('button[aria-label="关闭"]')!.click());
    await act(async () => { synthesis.resolve({ audio_base64: "late", format: "mp3" }); });
    assert.equal(commands.includes("preview.play"), false);
    assert.equal(commands.includes("preview.stop"), true);
  } finally { await view.cleanup(); }
});
