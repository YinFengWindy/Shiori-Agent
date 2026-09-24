/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { formatShortcut, resolveGlobalShortcut, type ShortcutKeyEvent, viewShortcutLabel } from "./globalShortcuts.js";

function key(overrides: Partial<ShortcutKeyEvent>): ShortcutKeyEvent {
  return {
    key: "",
    code: "",
    ctrlKey: true,
    metaKey: false,
    altKey: false,
    shiftKey: false,
    isComposing: false,
    keyCode: 0,
    repeat: false,
    ...overrides,
  };
}

describe("resolveGlobalShortcut", () => {
  it("maps Ctrl+K, Ctrl+, and Ctrl+digit", () => {
    assert.deepEqual(resolveGlobalShortcut(key({ key: "k", code: "KeyK" }), false), { kind: "search" });
    assert.deepEqual(resolveGlobalShortcut(key({ key: ",", code: "Comma" }), false), { kind: "settings" });
    assert.deepEqual(resolveGlobalShortcut(key({ key: "1", code: "Digit1" }), false), { kind: "view", index: 0 });
    assert.deepEqual(resolveGlobalShortcut(key({ key: "9", code: "Digit9" }), false), { kind: "view", index: 8 });
  });

  it("reads the physical key so non-QWERTY layouts still work", () => {
    // AZERTY: the Digit1 key types "&" without Shift.
    assert.deepEqual(resolveGlobalShortcut(key({ key: "&", code: "Digit1" }), false), { kind: "view", index: 0 });
  });

  it("falls back to the character for synthetic events without a code", () => {
    assert.deepEqual(resolveGlobalShortcut(key({ key: "K" }), false), { kind: "search" });
    assert.deepEqual(resolveGlobalShortcut(key({ key: "2" }), false), { kind: "view", index: 1 });
  });

  it("ignores IME composition, auto-repeat and unrelated chords", () => {
    assert.equal(resolveGlobalShortcut(key({ key: "k", code: "KeyK", isComposing: true }), false), null);
    assert.equal(resolveGlobalShortcut(key({ key: "Process", code: "KeyK", keyCode: 229 }), false), null);
    assert.equal(resolveGlobalShortcut(key({ key: "k", code: "KeyK", repeat: true }), false), null);
    assert.equal(resolveGlobalShortcut(key({ key: "k", code: "KeyK", ctrlKey: false }), false), null);
    assert.equal(resolveGlobalShortcut(key({ key: "K", code: "KeyK", shiftKey: true }), false), null);
    assert.equal(resolveGlobalShortcut(key({ key: "1", code: "Digit1", altKey: true }), false), null);
    assert.equal(resolveGlobalShortcut(key({ key: "0", code: "Digit0" }), false), null);
    assert.equal(resolveGlobalShortcut(key({ key: "c", code: "KeyC" }), false), null);
  });

  it("uses the command key instead of Ctrl on macOS", () => {
    assert.deepEqual(resolveGlobalShortcut(key({ key: "k", code: "KeyK", ctrlKey: false, metaKey: true }), true), { kind: "search" });
    assert.equal(resolveGlobalShortcut(key({ key: "k", code: "KeyK" }), true), null);
    assert.equal(resolveGlobalShortcut(key({ key: "k", code: "KeyK", metaKey: true }), false), null);
  });
});

describe("shortcut labels", () => {
  it("formats per platform and stops after nine views", () => {
    assert.equal(formatShortcut("K", false), "Ctrl+K");
    assert.equal(formatShortcut("K", true), "⌘K");
    assert.equal(viewShortcutLabel(0, false), "Ctrl+1");
    assert.equal(viewShortcutLabel(9, false), undefined);
  });
});
