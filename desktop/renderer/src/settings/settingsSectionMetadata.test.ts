/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  createInitialSettingsSubsectionState,
  resolveSettingsSubsectionId,
  settingsSubsections,
} from "./settingsSectionMetadata.js";

describe("settingsSectionMetadata", () => {
  it("keeps every configured subsection attached to its owning domain", () => {
    assert.deepEqual(settingsSubsections.models.map((item) => item.id), ["main", "fast", "agent", "vl"]);
    assert.deepEqual(settingsSubsections.channels.map((item) => item.id), ["telegram", "qq", "qqbot"]);
  });

  it("falls back to the first subsection when persisted selection is invalid", () => {
    const active = createInitialSettingsSubsectionState();
    active.models = "removed-model-section";

    assert.equal(resolveSettingsSubsectionId("models", active), "main");
  });
});
