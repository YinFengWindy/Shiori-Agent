import assert from "node:assert/strict";
import { before, test } from "node:test";
import { act, useState } from "react";
import { PluginHostServicesProvider } from "@yinfengwindy/shiori-sdk";
import { changeInputValue, createFakeHostServices, createFakePluginClient, deferred, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import type { RoleVoice } from "../shared/contracts";
let ReferenceList: typeof import("./ReferenceList").ReferenceList;
before(async () => { const view = await mountTestComponent(null); ({ ReferenceList } = await import("./ReferenceList")); await view.cleanup(); });

const voice: RoleVoice = { text_lang: "auto", speed: 1, default: { asset: "default.wav", prompt_text: "平静参考", prompt_lang: "zh", duration: 4.2 }, moods: {
  开心: { asset: "happy.wav", prompt_text: "开心参考", prompt_lang: "zh", duration: 3.5 },
} };

/** Mounts the list over an in-memory draft, recording whether each edit was an `update` or a `commit`. */
async function mount(options: { moodCatalog?: string[]; pickFiles?: () => Promise<string[]>; importResult?: Promise<unknown> } = {}) {
  const fake = createFakeHostServices({ pickFiles: options.pickFiles ?? (async () => ["clip.wav"]) });
  const client = createFakePluginClient({ call: async <T,>() => await (options.importResult ?? Promise.resolve({ asset: "imported.wav", duration: 5.25 })) as T });
  const edits: Array<{ kind: "update" | "commit"; voice: RoleVoice }> = [];
  const previews: string[] = [];
  let draft = voice;
  function Host() {
    const [, rerender] = useState(0);
    const edit = (kind: "update" | "commit") => (change?: (current: RoleVoice) => RoleVoice) => {
      if (change) draft = change(draft);
      edits.push({ kind, voice: draft });
      rerender((count) => count + 1);
    };
    return <ReferenceList roleId="role" client={client} voice={{ draft, update: edit("update"), commit: edit("commit") }} moodCatalog={options.moodCatalog ?? []}
      disabled={false} previewDisabled={false} onPreview={(mood) => previews.push(mood)} />;
  }
  const view = await mountTestComponent(<PluginHostServicesProvider services={fake.host}><Host /></PluginHostServicesProvider>);
  const row = (title: string) => view.container.querySelector<HTMLElement>(`li[data-reference="${title}"]`);
  const click = (element: Element | null | undefined) => act(async () => (element as HTMLButtonElement).click());
  return { view, row, click, edits, previews };
}

test("a catalog mood without audio becomes a reference in one import, committed at once", async () => {
  const ui = await mount({ moodCatalog: ["开心", "生气"] });
  try {
    assert.equal(ui.row("开心")!.querySelector("button[aria-expanded]") !== null, true, "a configured catalog mood keeps its compact row");
    await ui.click(ui.row("生气")!.querySelector("button"));
    assert.deepEqual(ui.edits.map((edit) => edit.kind), ["commit"]);
    assert.deepEqual(ui.edits[0].voice.moods.生气, { asset: "imported.wav", duration: 5.25, prompt_text: "", prompt_lang: "zh" });
    await ui.click(ui.row("生气")!.querySelector('[aria-label="试听生气"]'));
    assert.deepEqual(ui.previews, ["生气"]);
  } finally { await ui.view.cleanup(); }
});

test("the import indicator stays on the row or form that started it", async () => {
  const done = deferred<unknown>();
  const ui = await mount({ moodCatalog: ["生气"], importResult: done.promise });
  try {
    await ui.click(ui.row("生气")!.querySelector("button"));
    assert.equal(ui.row("生气")!.querySelector("button")!.textContent, "导入中…");
    const add = Array.from(ui.view.container.querySelectorAll("button")).find((item) => item.textContent === "添加情绪");
    assert.ok(add, "the custom form is not marked busy by a row's import");
    await act(async () => { done.resolve({ asset: "angry.wav", duration: 3 }); await done.promise; });
  } finally { await ui.view.cleanup(); }
});

test("a custom mood is added only after a successful import; a cancelled picker leaves nothing", async () => {
  let picked: string[] = [];
  const ui = await mount({ pickFiles: async () => picked });
  try {
    await changeInputValue(ui.view.container.querySelector<HTMLInputElement>('[aria-label="情绪名称"]')!, "害羞");
    const add = () => ui.click(Array.from(ui.view.container.querySelectorAll("button")).find((item) => item.textContent === "添加情绪"));
    await add();
    assert.equal(ui.row("害羞"), null);
    assert.equal(ui.edits.length, 0);
    picked = ["shy.wav"];
    await add();
    assert.ok(ui.row("害羞")?.querySelector('[aria-label="试听害羞"]'));
    assert.deepEqual(Object.keys(ui.edits.at(-1)!.voice.moods), ["开心", "害羞"]);
  } finally { await ui.view.cleanup(); }
});

test("one row expands at a time; transcript typing is an update, language and delete are commits", async () => {
  const ui = await mount();
  const expanded = () => Array.from(ui.view.container.querySelectorAll('button[aria-expanded="true"]'), (item) => item.closest("li")!.dataset.reference);
  try {
    await ui.click(ui.row("默认参考")!.querySelector("button[aria-expanded]"));
    await ui.click(ui.row("开心")!.querySelector("button[aria-expanded]"));
    assert.deepEqual(expanded(), ["开心"]);
    await changeInputValue(ui.view.container.querySelector<HTMLTextAreaElement>('[aria-label="开心参考转写"]')!, "新的转写");
    assert.deepEqual(ui.edits.at(-1), { kind: "update", voice: { ...voice, moods: { 开心: { ...voice.moods.开心, prompt_text: "新的转写" } } } });
    await ui.click(ui.row("开心")!.querySelector('[aria-label="删除开心"]'));
    assert.deepEqual(ui.edits.at(-1), { kind: "commit", voice: { ...voice, moods: {} } });
    assert.deepEqual(expanded(), []);
  } finally { await ui.view.cleanup(); }
});
