/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { shouldProcessDesktopBridgeEventSynchronously } from "./desktopBridgeEventPriority";

describe("shouldProcessDesktopBridgeEventSynchronously", () => {
  it("processes chat state events in arrival order", () => {
    const methods = [
      "bridge.exit",
      "chat.delta",
      "chat.done",
      "chat.error",
      "session.updated",
    ];

    methods.forEach((method) => {
      assert.equal(shouldProcessDesktopBridgeEventSynchronously(method), true);
    });
  });

  it("allows non-critical renderer events to use a transition", () => {
    const methods = ["window.state", "roles.updated", "diagnostics.updated"];

    methods.forEach((method) => {
      assert.equal(shouldProcessDesktopBridgeEventSynchronously(method), false);
    });
  });
});
