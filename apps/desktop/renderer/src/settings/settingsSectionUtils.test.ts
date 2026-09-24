/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  appendStringListItem,
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
      { value: "", label: "默认" },
      { value: "memory2", label: "memory2" },
    ]);
  });
});

describe("appendStringListItem", () => {
  it("trims, and ignores blank or duplicate entries", () => {
    assert.deepEqual(appendStringListItem(["a"], "  b "), ["a", "b"]);
    assert.deepEqual(appendStringListItem(["a"], "a"), ["a"]);
    assert.deepEqual(appendStringListItem(["a"], "   "), ["a"]);
  });
});
