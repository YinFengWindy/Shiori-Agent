import assert from "node:assert/strict";
import { before, describe, it } from "node:test";
import type React from "react";
import { act } from "react";
import { mountTestComponent } from "../../../apps/desktop/renderer/src/shared/testing/domTestHarness";
import { chooseSelectOption } from "../../../apps/desktop/renderer/src/shared/testing/selectTestActions";
import type { RoleRecord } from "../../../apps/desktop/renderer/src/shared/types";
import { initialStudioForm } from "./novelAiPageStore";
import type { ImageStudioFormState } from "./types";
import type { NovelAiPromptSettings } from "./useNovelAiPromptSettings";

let PromptPanel: typeof import("./PromptPanel").PromptPanel;
before(async () => {
  // Base UI picks its layout-effect flavour when first loaded; load it inside a DOM.
  const environment = await mountTestComponent(null);
  ({ PromptPanel } = await import("./PromptPanel"));
  await environment.cleanup();
});

/** Mounts inside a DOM whose bridge can turn file paths into asset URLs (role avatars). */
async function mountPanel(element: React.ReactElement) {
  const view = await mountTestComponent(null);
  Object.defineProperty(window, "miraDesktop", { configurable: true, value: { localAssetUrl: (path: string) => `asset://${path}` } });
  await view.render(element);
  return view;
}

const roles = [
  { id: "rin", name: "雨宫凛", avatar_abs: "D:/a/rin.webp" },
  { id: "kaede", name: "枫", avatar_abs: null },
] as unknown as RoleRecord[];

function settings(presets: number[]): NovelAiPromptSettings {
  return {
    nsfwEnabled: false, addQualityTags: true, undesiredContentPreset: 0, model: "nai-diffusion-4-5-curated",
    setNsfwEnabled: () => undefined, setAddQualityTags: () => undefined, setUndesiredContentPreset: (value) => presets.push(value),
  };
}

function button(name: string): HTMLButtonElement {
  const found = Array.from(document.querySelectorAll<HTMLButtonElement>("button")).find((element) => (element.getAttribute("aria-label") ?? element.textContent?.trim()) === name);
  assert.ok(found, `Missing button: ${name}`);
  return found;
}

describe("PromptPanel", () => {
  it("edits the positive and negative prompt through full Chinese tabs, and picks size and role", async () => {
    const changes: Partial<ImageStudioFormState>[] = [];
    const panel = (roleId: string) => <PromptPanel form={{ ...initialStudioForm, roleId, prompt: "1girl" }} roles={roles} settings={settings([])}
      submitting={false} canSubmit validationError="" onChange={(next) => changes.push(next)} onPickBaseImage={() => undefined} onSubmit={() => undefined} />;
    const view = await mountPanel(panel("kaede"));
    try {
      const tabs = Array.from(view.container.querySelectorAll('[role="radio"]')).map((element) => element.textContent);
      assert.deepEqual(tabs, ["正向提示词", "负向提示词"]);
      await act(async () => button("负向提示词").click());
      const textarea = view.container.querySelector<HTMLTextAreaElement>('textarea[aria-label="负向提示词"]');
      assert.ok(textarea, "the negative tab edits the negative prompt");

      await chooseSelectOption("尺寸", "竖图 · 832 × 1216");
      await chooseSelectOption("生成角色", "雨宫凛");
      assert.deepEqual(changes, [{ sizePreset: "portrait" }, { roleId: "rin" }]);
      await view.render(panel("rin"));
      const trigger = document.querySelector('[role="combobox"][aria-label="生成角色"]');
      assert.ok(trigger?.querySelector("img"), "the role picker shows the selected role's avatar");
    } finally { await view.cleanup(); }
  });

  it("commits the undesired-content preset from the settings popover without closing it", async () => {
    const presets: number[] = [];
    const view = await mountPanel(<PromptPanel form={initialStudioForm} roles={roles} settings={settings(presets)} submitting={false} canSubmit={false}
      validationError="" onChange={() => undefined} onPickBaseImage={() => undefined} onSubmit={() => undefined} />);
    try {
      await act(async () => button("生成设置").click());
      await act(async () => button("重度").click());
      assert.deepEqual(presets, [2]);
      assert.ok(view.container.querySelector('[role="dialog"][aria-label="生成设置"]'), "the popover stays open after a choice");
      await act(async () => {
        window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
      });
      assert.equal(view.container.querySelector('[role="dialog"]'), null);
    } finally { await view.cleanup(); }
  });

  it("disables 生成 when the form cannot be submitted and says so while generating", async () => {
    let submits = 0;
    const view = await mountPanel(<PromptPanel form={initialStudioForm} roles={roles} settings={settings([])} submitting canSubmit={false}
      validationError="" onChange={() => undefined} onPickBaseImage={() => undefined} onSubmit={() => { submits += 1; }} />);
    try {
      const generate = button("生成中…");
      assert.equal(generate.disabled, true);
      assert.equal(generate.getAttribute("aria-busy"), "true");
      await act(async () => generate.click());
      assert.equal(submits, 0);
    } finally { await view.cleanup(); }
  });
});
