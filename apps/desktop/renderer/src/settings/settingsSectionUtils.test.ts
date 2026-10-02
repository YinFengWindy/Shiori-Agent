/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  getMemoryEngineOptions,
  parseCompleteSettingsNumber,
} from "./settingsSectionUtils.js";

describe("settingsSectionUtils", () => {
  it("parses only complete numbers, leaving empty and intermediate text unreported", () => {
    for (const text of ["", " ", "invalid", "0.", "-", "1e", "."]) assert.equal(parseCompleteSettingsNumber(text), null);
    assert.equal(parseCompleteSettingsNumber("24"), 24);
    assert.equal(parseCompleteSettingsNumber("0.8"), 0.8);
  });

  it("keeps a configured custom memory engine selectable", () => {
    assert.deepEqual(getMemoryEngineOptions("memory2"), [
      { value: "", label: "默认" },
      { value: "memory2", label: "memory2" },
    ]);
  });
});
