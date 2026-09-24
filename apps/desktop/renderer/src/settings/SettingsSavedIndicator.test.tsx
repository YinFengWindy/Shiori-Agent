import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act, useState } from "react";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import type { SettingsSavePhase } from "./settingsPageTypes";
import { SettingsSavedIndicator } from "./SettingsSavedIndicator";
import { settingsSavedIndicatorMs } from "./settingsSaveState";

async function mountIndicator() {
  let setPhase!: (phase: SettingsSavePhase) => void;
  function Harness() {
    const [phase, update] = useState<SettingsSavePhase>("idle");
    setPhase = update;
    return <SettingsSavedIndicator phase={phase} />;
  }
  const view = await mountTestComponent(<Harness />);
  const indicator = () => view.container.querySelector('[data-testid="settings-saved-indicator"]')!;
  return {
    view,
    visible: () => indicator().getAttribute("aria-hidden") !== "true",
    phase: async (phase: SettingsSavePhase) => { await act(async () => setPhase(phase)); },
  };
}

describe("SettingsSavedIndicator", () => {
  it("confirms a completed save, then fades on its own", async () => {
    const harness = await mountIndicator();
    try {
      assert.equal(harness.visible(), false);
      await harness.phase("saving");
      assert.equal(harness.visible(), false);
      await harness.phase("idle");
      assert.equal(harness.visible(), true);
      await act(async () => { await new Promise((resolve) => setTimeout(resolve, settingsSavedIndicatorMs + 100)); });
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
