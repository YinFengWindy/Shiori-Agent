/// <reference types="node" />

import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { act } from "react";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { appearancePrefsStorageKey } from "../shared/appearancePrefs";
import { resetAppearancePrefsCache } from "../shared/useAppearancePrefs";
import type { SettingsFormData } from "../shared/types";
import { AppearanceSettingsSection } from "./AppearanceSettingsSection";
import { createSettingsDraft } from "./testFixtures";

afterEach(() => resetAppearancePrefsCache());

function renderSection(draft: SettingsFormData = createSettingsDraft(), onDraft: (next: SettingsFormData) => void = () => undefined) {
  return <AppearanceSettingsSection draft={draft} updateDraft={(mutate) => onDraft(mutate(draft))} />;
}

describe("AppearanceSettingsSection", () => {
  it("shows 背景呼吸与视差 on by default and persists turning it off", async () => {
    resetAppearancePrefsCache();
    const view = await mountTestComponent(renderSection());
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
      await view.render(renderSection());
      const toggle = view.container.querySelector('[role="switch"][aria-label="背景呼吸与视差"]');
      assert.equal(toggle?.getAttribute("aria-checked"), "false");
    } finally {
      await view.cleanup();
    }
  });

  it("edits streaming_enabled (moved here from 高级) through the shared settings draft", async () => {
    resetAppearancePrefsCache();
    const draft = createSettingsDraft();
    draft.advanced.streamingEnabled = true;
    let saved: SettingsFormData | null = null;
    const view = await mountTestComponent(renderSection(draft, (next) => { saved = next; }));
    try {
      const toggle = view.container.querySelector<HTMLButtonElement>('[role="switch"][aria-label="实时显示回复"]');
      assert.equal(toggle?.getAttribute("aria-checked"), "true");
      await act(async () => toggle!.click());
      assert.equal(saved!.advanced.streamingEnabled, false);
    } finally {
      await view.cleanup();
    }
  });
});
