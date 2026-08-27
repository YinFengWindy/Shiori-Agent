/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  getMemoryEngineOptions,
  parseSettingsNumber,
} from "./settingsSectionUtils.js";

describe("settingsSectionUtils", () => {
  it("preserves invalid numeric input fallback values", () => {
    assert.equal(parseSettingsNumber("invalid", 12), 12);
    assert.equal(parseSettingsNumber("24", 12), 24);
  });

  it("keeps a configured custom memory engine selectable", () => {
    assert.deepEqual(getMemoryEngineOptions("memory2"), [
      { value: "", label: "default" },
      { value: "memory2", label: "memory2" },
    ]);
  });
});
