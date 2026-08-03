/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { formatStoryDateTime } from "./storyDateTime";

describe("formatStoryDateTime", () => {
  it("formats Story timestamps as Beijing date and minute", () => {
    assert.equal(formatStoryDateTime("2026-08-02T14:25:46.791880+00:00"), "2026-08-02 22:25");
  });

  it("returns an empty display value for invalid timestamps", () => {
    assert.equal(formatStoryDateTime("invalid"), "");
  });
});
