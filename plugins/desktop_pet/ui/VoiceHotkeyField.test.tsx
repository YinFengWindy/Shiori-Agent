import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { changeInputValue, createFakePluginClient, deferred, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { VoiceHotkeyField } from "./VoiceHotkeyField";

/** Mounts the field; `validate` answers `voice.preferences.validate`, `commits` records what reached the draft. */
async function mountField(validate: (hotkey: string) => Promise<void>) {
  const commits: string[] = [];
  const client = createFakePluginClient({
    background: {
      call: async <T,>(method: string, payload?: Record<string, unknown>) => {
        assert.equal(method, "voice.preferences.validate");
        await validate(String(payload?.hotkey));
        return undefined as T;
      },
    },
  });
  const view = await mountTestComponent(<VoiceHotkeyField client={client} value="Ctrl+Space" onCommit={(hotkey) => commits.push(hotkey)} />);
  const input = view.container.querySelector<HTMLInputElement>('input[aria-label="快捷键"]')!;
  return { view, input, commits };
}

const blur = (input: HTMLInputElement) => act(async () => { input.dispatchEvent(new FocusEvent("focusout", { bubbles: true })); });
const press = (input: HTMLInputElement, key: string) => act(async () => { input.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true })); });

test("typing alone commits nothing; a valid hotkey commits on blur and on Enter", async () => {
  const { view, input, commits } = await mountField(async () => undefined);
  try {
    await changeInputValue(input, "Alt+Space");
    assert.deepEqual(commits, []);
    await blur(input);
    assert.deepEqual(commits, ["Alt+Space"]);
    await changeInputValue(input, "Ctrl+Shift+V");
    await press(input, "Enter");
    assert.deepEqual(commits, ["Alt+Space", "Ctrl+Shift+V"]);
  } finally { await view.cleanup(); }
});

test("an invalid hotkey stays visible with its error and is never committed; Escape returns to the saved one", async () => {
  const { view, input, commits } = await mountField(async () => { throw new Error("快捷键格式无效"); });
  try {
    await changeInputValue(input, "not-a-key");
    await blur(input);
    await press(input, "Enter");
    assert.deepEqual(commits, []);
    assert.equal(input.value, "not-a-key");
    assert.equal(input.getAttribute("aria-invalid"), "true");
    assert.match(view.container.textContent ?? "", /快捷键格式无效/);
    await press(input, "Escape");
    assert.equal(input.value, "Ctrl+Space");
    assert.doesNotMatch(view.container.textContent ?? "", /快捷键格式无效/);
  } finally { await view.cleanup(); }
});

test("a validation that finishes after the field is gone commits nothing", async () => {
  const pending = deferred<void>();
  const { view, input, commits } = await mountField(() => pending.promise);
  await changeInputValue(input, "Alt+Space");
  await blur(input);
  await view.cleanup();
  await act(async () => pending.resolve());
  assert.deepEqual(commits, []);
});
