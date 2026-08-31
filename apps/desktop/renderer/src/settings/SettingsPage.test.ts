import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  settingsContentClass,
  settingsPageSurfaceClass,
  settingsToolbarClass,
} from "./SettingsPage";

describe("SettingsPage layout", () => {
  it("uses a white surface throughout the settings body", () => {
    assert.match(settingsPageSurfaceClass, /bg-white/);
    assert.match(settingsToolbarClass, /bg-white/);
    assert.match(settingsContentClass, /bg-white/);
  });

  it("keeps the toolbar persistently visible in layout flow", () => {
    assert.doesNotMatch(settingsToolbarClass, /settings-hover-toolbar/);
    assert.doesNotMatch(settingsToolbarClass, /absolute/);
    assert.doesNotMatch(settingsContentClass, /h-full/);
  });

  it("aligns toolbar and content gutters so both columns share one rhythm", () => {
    assert.match(settingsToolbarClass, /border-b border-stroke/);
    assert.match(settingsToolbarClass, /px-4 py-3 sm:px-6 lg:px-8/);
    assert.match(settingsContentClass, /px-4 py-6 sm:px-6 lg:px-8 lg:py-8/);
  });
});
