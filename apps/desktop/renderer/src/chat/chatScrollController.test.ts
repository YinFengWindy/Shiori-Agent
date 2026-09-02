/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { getChatSessionResetScrollBehavior } from "./chatScrollController";

describe("getChatSessionResetScrollBehavior", () => {
  it("jumps to the bottom on the first session load", () => {
    assert.equal(getChatSessionResetScrollBehavior("", "role:mira"), "auto");
  });

  it("smoothly moves to the bottom when switching between loaded sessions", () => {
    assert.equal(getChatSessionResetScrollBehavior("role:shiori", "role:mira"), "smooth");
  });
});
