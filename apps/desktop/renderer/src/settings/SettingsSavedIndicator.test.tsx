import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act, useState } from "react";
import { mockableWindowTimers, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import type { SettingsSavePhase } from "./settingsPageTypes";
import { SettingsSavedIndicator } from "./SettingsSavedIndicator";
import { settingsSavedIndicatorMs } from "./settingsSaveState";

async function mountIndicator(showPending = false) {
  let setPhase!: (phase: SettingsSavePhase) => void;
  function Harness() {
    const [phase, update] = useState<SettingsSavePhase>("idle");
    setPhase = update;
    return <SettingsSavedIndicator phase={phase} showPending={showPending} />;
  }
  const view = await mountTestComponent(<Harness />, { windowGlobals: mockableWindowTimers });
  const indicator = () => view.container.querySelector('[data-testid="settings-saved-indicator"]')!;
  return {
    view,
    text: () => indicator().textContent,
    visible: () => indicator().getAttribute("aria-hidden") !== "true",
    phase: async (phase: SettingsSavePhase) => { await act(async () => setPhase(phase)); },
  };
}

describe("SettingsSavedIndicator", () => {
  it("confirms a completed save, then fades on its own", async (t) => {
    t.mock.timers.enable({ apis: ["setTimeout"] });
    const harness = await mountIndicator();
    try {
      assert.equal(harness.visible(), false);
      await harness.phase("saving");
      assert.equal(harness.visible(), false);
      await harness.phase("idle");
      assert.equal(harness.visible(), true);
      await act(async () => t.mock.timers.tick(settingsSavedIndicatorMs - 1));
      assert.equal(harness.visible(), true);
      await act(async () => t.mock.timers.tick(1));
      assert.equal(harness.visible(), false);
    } finally { await harness.view.cleanup(); }
  });

  it("never claims a failed save was saved", async () => {
    const harness = await mountIndicator();
    try {
      await harness.phase("saving");
      await harness.phase("error");
      assert.equal(harness.visible(), false);
    } finally { await harness.view.cleanup(); }
  });
});


it("optionally shows unsaved work without leaving the previous saved label visible", async () => {
  const harness = await mountIndicator(true);
  try {
    await harness.phase("saving");
    assert.equal(harness.visible(), true);
    assert.equal(harness.text(), "正在保存…");
    await harness.phase("idle");
    assert.equal(harness.visible(), true);
    assert.equal(harness.text(), "已保存");
    await harness.phase("saving");
    assert.equal(harness.visible(), true);
    assert.equal(harness.text(), "正在保存…");
    await harness.phase("unknown");
    assert.equal(harness.visible(), false);
  } finally { await harness.view.cleanup(); }
});
