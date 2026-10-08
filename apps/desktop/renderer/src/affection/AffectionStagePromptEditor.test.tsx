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

/** A bridge holding one role's overrides, applying writes like the backend. */
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
        if (text && text.trim() && text.trim() !== defaults[stage]) overrides[stage] = text.trim();
        else delete overrides[stage];
      }
    }
    return { id: "test", type: "response", method, error: null, payload: answer() };
  };
  return { invoke, writes, overrides };
}

async function mountEditor(invoke: DesktopInvoke) {
  return mountTestComponent(<AffectionStagePromptEditor invoke={invoke} roleId="mira" />, {
    windowGlobals: { miraDesktop: { onEvent: () => () => {} } },
  });
}

const fields = (container: HTMLElement) => Array.from(container.querySelectorAll("textarea"));
const restoreButtons = (container: HTMLElement) => Array.from(container.querySelectorAll("button")).filter((button) => button.textContent === "恢复默认");

it("prefills every stage, saves a run of edits once they pause, and shows them again when reopened", async (t: TestContext) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const bridge = fakeBridge({ 熟悉: "嘴硬心软。" });
  const view = await mountEditor(bridge.invoke);
  try {
    assert.deepEqual(fields(view.container).map((field) => field.value), ["客气。", "嘴硬心软。", "随意。", "温柔。", "依恋。"]);
    assert.equal(restoreButtons(view.container).length, 1);

    await changeInputValue(fields(view.container)[0], "冷");
    await changeInputValue(fields(view.container)[0], "冷淡。");
    assert.equal(bridge.writes.length, 0);
    await act(async () => t.mock.timers.tick(400));
    assert.equal(bridge.writes.length, 1);
    assert.deepEqual(bridge.overrides, { 陌生: "冷淡。", 熟悉: "嘴硬心软。" });
    assert.equal(restoreButtons(view.container).length, 2);
  } finally {
    await view.cleanup();
  }

  const reopened = await mountEditor(bridge.invoke);
  try {
    assert.equal(fields(reopened.container)[0].value, "冷淡。");
  } finally {
    await reopened.cleanup();
  }
});

it("restores one stage's default at once and hides its 恢复默认", async () => {
  const bridge = fakeBridge({ 熟悉: "嘴硬心软。", 挚爱: "黏人。" });
  const view = await mountEditor(bridge.invoke);
  try {
    await act(async () => restoreButtons(view.container)[0].click());
    assert.deepEqual(bridge.writes, [{ 陌生: null, 熟悉: null, 朋友: null, 亲密: null, 挚爱: "黏人。" }]);
    assert.equal(fields(view.container)[1].value, "放松。");
    assert.equal(restoreButtons(view.container).length, 1);
    assert.deepEqual(bridge.overrides, { 挚爱: "黏人。" });
  } finally {
    await view.cleanup();
  }
});
