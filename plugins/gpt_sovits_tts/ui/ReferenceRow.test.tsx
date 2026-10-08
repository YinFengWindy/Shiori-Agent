import assert from "node:assert/strict";
import { before, test } from "node:test";
import { act, type ComponentProps } from "react";
import { changeInputValue, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
let ReferenceRow: typeof import("./ReferenceRow").ReferenceRow;
before(async () => { const view = await mountTestComponent(null); ({ ReferenceRow } = await import("./ReferenceRow")); await view.cleanup(); });

type Props = ComponentProps<typeof import("./ReferenceRow").ReferenceRow>;

function props(calls: string[], overrides: Partial<Props> = {}): Props {
  return {
    title: "开心", value: { asset: "a.wav", prompt_text: "今天真开心", prompt_lang: "zh", duration: 3.46 },
    expanded: false, disabled: false, importing: false, previewDisabled: false,
    onToggle: () => calls.push("toggle"), onImport: () => calls.push("import"), onPreview: () => calls.push("preview"), onDelete: () => calls.push("delete"),
    onTranscript: (text) => calls.push(`transcript:${text}`), onLanguage: (language) => calls.push(`language:${language}`),
    ...overrides,
  };
}

const ul = (row: Props) => <ul><ReferenceRow {...row} /></ul>;

test("a configured row shows name, duration and transcript excerpt with its own actions; expanding edits transcript and language", async () => {
  const calls: string[] = [];
  const view = await mountTestComponent(ul(props(calls)));
  const click = (selector: string) => act(async () => view.container.querySelector<HTMLButtonElement>(selector)!.click());
  try {
    const header = view.container.querySelector<HTMLButtonElement>("button[aria-expanded]")!;
    assert.equal(header.getAttribute("aria-expanded"), "false");
    assert.match(header.textContent ?? "", /开心.*3\.5 秒.*今天真开心/);
    assert.equal(view.container.querySelector("textarea"), null);
    await click("button[aria-expanded]");
    await click('[aria-label="试听开心"]');
    await click('[aria-label="更换开心音频"]');
    await click('[aria-label="删除开心"]');
    assert.deepEqual(calls, ["toggle", "preview", "import", "delete"]);

    await view.render(ul(props(calls, { expanded: true })));
    await changeInputValue(view.container.querySelector<HTMLTextAreaElement>('[aria-label="开心参考转写"]')!, "改过的转写");
    assert.equal(calls.at(-1), "transcript:改过的转写");
    assert.ok(view.container.querySelector('[aria-label="开心参考语言"]'));
  } finally { await view.cleanup(); }
});

test("a reference without audio only offers the import and shows where an import is running", async () => {
  const calls: string[] = [];
  const view = await mountTestComponent(ul(props(calls, { value: null })));
  try {
    assert.equal(view.container.querySelector("button[aria-expanded]"), null);
    const importButton = view.container.querySelector<HTMLButtonElement>("button")!;
    assert.equal(importButton.textContent, "导入音频");
    await act(async () => importButton.click());
    assert.deepEqual(calls, ["import"]);
    await view.render(ul(props(calls, { value: null, importing: true, disabled: true })));
    assert.equal(view.container.querySelector("button")!.textContent, "导入中…");
  } finally { await view.cleanup(); }
});

test("an older reference without a measured duration shows a dash", async () => {
  const view = await mountTestComponent(ul(props([], { value: { asset: "a.wav", prompt_text: "", prompt_lang: "zh", duration: null } })));
  try { assert.match(view.container.textContent ?? "", /开心—/); } finally { await view.cleanup(); }
});
