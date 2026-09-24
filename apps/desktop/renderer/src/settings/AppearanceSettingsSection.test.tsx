/// <reference types="node" />

import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { act } from "react";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { appearancePrefsStorageKey } from "../shared/appearancePrefs";
import { resetAppearancePrefsCache } from "../shared/useAppearancePrefs";
import { AppearanceSettingsSection } from "./AppearanceSettingsSection";

afterEach(() => resetAppearancePrefsCache());

describe("AppearanceSettingsSection", () => {
  it("shows 背景呼吸与视差 on by default and persists turning it off", async () => {
    resetAppearancePrefsCache();
    const view = await mountTestComponent(<AppearanceSettingsSection />);
    try {
      const toggle = view.container.querySelector<HTMLButtonElement>('[role="switch"][aria-label="背景呼吸与视差"]');
      assert.ok(toggle);
      assert.equal(toggle.getAttribute("aria-checked"), "true");
      await act(async () => toggle.click());
      assert.equal(toggle.getAttribute("aria-checked"), "false");
      assert.deepEqual(JSON.parse(window.localStorage.getItem(appearancePrefsStorageKey)!), { version: 1, backdropMotion: false });
    } finally {
      await view.cleanup();
    }
  });

  it("reads a stored preference on first render", async () => {
    resetAppearancePrefsCache();
    const view = await mountTestComponent(<div />);
    try {
      window.localStorage.setItem(appearancePrefsStorageKey, JSON.stringify({ version: 1, backdropMotion: false }));
      await view.render(<AppearanceSettingsSection />);
      const toggle = view.container.querySelector('[role="switch"]');
      assert.equal(toggle?.getAttribute("aria-checked"), "false");
    } finally {
      await view.cleanup();
    }
  });
});
