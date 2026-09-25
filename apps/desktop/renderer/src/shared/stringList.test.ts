/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { appendStringListItem } from "./stringList.js";

describe("appendStringListItem", () => {
  it("trims, and ignores blank or duplicate entries", () => {
    assert.deepEqual(appendStringListItem(["a"], "  b "), ["a", "b"]);
    assert.deepEqual(appendStringListItem(["a"], "a"), ["a"]);
    assert.deepEqual(appendStringListItem(["a"], "   "), ["a"]);
  });
});
