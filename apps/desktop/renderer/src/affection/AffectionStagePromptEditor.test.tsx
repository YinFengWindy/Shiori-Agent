import assert from "node:assert/strict";
import { before, it, type TestContext } from "node:test";
import { act } from "react";
import { changeInputValue, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import type { DesktopInvoke } from "../shared/bridgeInvoke";
import type { AffectionStagePromptChanges } from "./affectionStagePrompts";

// Base UI binds DOM globals at import time, so the editor loads inside a test window.
let AffectionStagePromptEditor: typeof import("./AffectionStagePromptEditor").AffectionStagePromptEditor;
before(async () => {
  const environment = await mountTestComponent(null);
  ({ AffectionStagePromptEditor } = await import("./AffectionStagePromptEditor"));
  await environment.cleanup();
});

const defaults: Record<string, string> = { 陌生: "客气。", 熟悉: "放松。", 朋友: "随意。", 亲密: "温柔。", 挚爱: "依恋。" };

/** A bridge holding one role's overrides: it stores each written text and drops each `null`. */
function fakeBridge(initial: Record<string, string>) {
  const overrides = { ...initial };
  const writes: AffectionStagePromptChanges[] = [];
  const answer = () => ({
    role_id: "mira",
    stages: Object.entries(defaults).map(([stage, fallback]) => ({
      stage, prompt: overrides[stage] ?? fallback, default: fallback, overridden: stage in overrides,
    })),
  });
  const invoke: DesktopInvoke = async ({ method, payload }) => {
    if (method === "roles.affection.stagePrompts.set") {
      const prompts = payload.prompts as AffectionStagePromptChanges;
      writes.push(prompts);
      for (const [stage, text] of Object.entries(prompts)) {
        if (text === null) delete overrides[stage];
        else overrides[stage] = text;
      }
    }
    return { id: "test", type: "response", method, error: null, payload: answer() };
  };
  return { invoke, writes, overrides };
}

async function mountEditor(invoke: DesktopInvoke, currentStage: string | null = null) {
  return mountTestComponent(<AffectionStagePromptEditor invoke={invoke} roleId="mira" currentStage={currentStage} />, {
    windowGlobals: { miraDesktop: { onEvent: () => () => {} } },
  });
}

const fields = (container: HTMLElement) => Array.from(container.querySelectorAll("textarea"));
const field = (container: HTMLElement) => {
  const [only, ...rest] = fields(container);
  assert.ok(only && rest.length === 0, "exactly one stage field shows");
  return only;
};
const tabs = (container: HTMLElement) => Array.from(container.querySelectorAll<HTMLButtonElement>('[role="tab"]'));
const selectedTab = (container: HTMLElement) => tabs(container).find((tab) => tab.getAttribute("aria-selected") === "true")?.textContent;
const customized = (container: HTMLElement) => tabs(container).filter((tab) => tab.querySelector('[data-testid="affection-stage-customized"]')).map((tab) => tab.textContent);
async function pick(container: HTMLElement, stage: string) {
  const tab = tabs(container).find((candidate) => candidate.textContent === stage);
  assert.ok(tab, `no tab for ${stage}`);
  await act(async () => tab.click());
}
const restoreButtons = (container: HTMLElement) => Array.from(container.querySelectorAll("button")).filter((button) => button.textContent === "恢复默认");

it("shows one stage at a time, prefilled, saves a run of edits once they pause, and shows them again when reopened", async (t: TestContext) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const bridge = fakeBridge({ 熟悉: "嘴硬心软。" });
  const view = await mountEditor(bridge.invoke);
  try {
    assert.deepEqual(tabs(view.container).map((tab) => tab.textContent), ["陌生", "熟悉", "朋友", "亲密", "挚爱"]);
    assert.equal(selectedTab(view.container), "陌生");
    assert.deepEqual(customized(view.container), ["熟悉"]);
    const shown: string[] = [];
    for (const stage of Object.keys(defaults)) {
      await pick(view.container, stage);
      shown.push(field(view.container).value);
    }
    assert.deepEqual(shown, ["客气。", "嘴硬心软。", "随意。", "温柔。", "依恋。"]);

    await pick(view.container, "陌生");
    assert.equal(restoreButtons(view.container).length, 0);
    await changeInputValue(field(view.container), "冷");
    await changeInputValue(field(view.container), "冷淡。");
    assert.equal(bridge.writes.length, 0);
    await act(async () => t.mock.timers.tick(400));
    // Only the edited stage is written, so other stages edited elsewhere stay as stored.
    assert.deepEqual(bridge.writes, [{ 陌生: "冷淡。" }]);
    assert.deepEqual(bridge.overrides, { 陌生: "冷淡。", 熟悉: "嘴硬心软。" });
    assert.equal(restoreButtons(view.container).length, 1);
    assert.deepEqual(customized(view.container), ["陌生", "熟悉"]);
  } finally {
    await view.cleanup();
  }

  const reopened = await mountEditor(bridge.invoke);
  try {
    assert.equal(field(reopened.container).value, "冷淡。");
  } finally {
    await reopened.cleanup();
  }
});

it("keeps unsaved edits across stage switches and saves every edited stage together", async (t: TestContext) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const bridge = fakeBridge({ 熟悉: "嘴硬心软。" });
  const view = await mountEditor(bridge.invoke, "熟悉");
  try {
    // It opens on the role's current stage.
    assert.equal(selectedTab(view.container), "熟悉");
    await changeInputValue(field(view.container), "不服气。");
    await pick(view.container, "朋友");
    assert.equal(field(view.container).value, "随意。");
    await changeInputValue(field(view.container), "打闹。");
    await pick(view.container, "熟悉");
    assert.equal(field(view.container).value, "不服气。");
    assert.equal(bridge.writes.length, 0);

    await act(async () => t.mock.timers.tick(400));
    assert.deepEqual(bridge.writes, [{ 熟悉: "不服气。", 朋友: "打闹。" }]);
    await pick(view.container, "朋友");
    assert.equal(field(view.container).value, "打闹。");
  } finally {
    await view.cleanup();
  }
});

it("restores one stage's default at once and hides its 恢复默认", async () => {
  const bridge = fakeBridge({ 熟悉: "嘴硬心软。", 挚爱: "黏人。" });
  const view = await mountEditor(bridge.invoke);
  try {
    await pick(view.container, "熟悉");
    await act(async () => restoreButtons(view.container)[0].click());
    assert.deepEqual(bridge.writes, [{ 熟悉: null }]);
    assert.equal(field(view.container).value, "放松。");
    assert.equal(restoreButtons(view.container).length, 0);
    assert.deepEqual(customized(view.container), ["挚爱"]);
    assert.deepEqual(bridge.overrides, { 挚爱: "黏人。" });
  } finally {
    await view.cleanup();
  }
});

it("keeps a stage changed elsewhere between two saves of another stage", async (t: TestContext) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const bridge = fakeBridge({});
  const view = await mountEditor(bridge.invoke);
  try {
    // Another editor sets 熟悉 after this one loaded.
    bridge.overrides["熟悉"] = "Y";
    await changeInputValue(field(view.container), "冷淡。");
    await act(async () => t.mock.timers.tick(400));
    await changeInputValue(field(view.container), "更冷淡。");
    await act(async () => t.mock.timers.tick(400));

    assert.deepEqual(bridge.writes, [{ 陌生: "冷淡。" }, { 陌生: "更冷淡。" }]);
    assert.deepEqual(bridge.overrides, { 熟悉: "Y", 陌生: "更冷淡。" });
  } finally {
    await view.cleanup();
  }
});

it("stays on a stage edited before the role's current stage is known", async (t: TestContext) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const bridge = fakeBridge({});
  const view = await mountEditor(bridge.invoke);
  try {
    assert.equal(selectedTab(view.container), "陌生");
    await changeInputValue(field(view.container), "有点拘谨。");
    // The history answers later with the role's stage; the field being typed in stays.
    await view.render(<AffectionStagePromptEditor invoke={bridge.invoke} roleId="mira" currentStage="朋友" />);
    assert.equal(selectedTab(view.container), "陌生");
    assert.equal(field(view.container).value, "有点拘谨。");
    await act(async () => t.mock.timers.tick(400));
    assert.deepEqual(bridge.writes, [{ 陌生: "有点拘谨。" }]);
  } finally {
    await view.cleanup();
  }
});
