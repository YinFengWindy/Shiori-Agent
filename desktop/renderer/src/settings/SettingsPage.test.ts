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
    assert.doesNotMatch(settingsPageSurfaceClass, /#F7F8FB/);
    assert.doesNotMatch(settingsToolbarClass, /#F7F8FB/);
  });

  it("reduces toolbar and content padding by four pixels", () => {
    assert.match(settingsToolbarClass, /px-3 py-3 sm:px-5 lg:px-7/);
    assert.match(settingsContentClass, /px-3 py-5 sm:px-5 lg:px-7 lg:py-7/);
  });
});
