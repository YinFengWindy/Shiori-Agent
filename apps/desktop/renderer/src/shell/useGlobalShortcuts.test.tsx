import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act } from "react";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { useGlobalShortcuts } from "./useGlobalShortcuts";

function Harness({ enabled = true, log }: { enabled?: boolean; log: string[] }) {
  useGlobalShortcuts({
    enabled,
    onSearch: () => log.push("search"),
    onSettings: () => log.push("settings"),
    views: [{ onSelect: () => log.push("view:0") }, { onSelect: () => log.push("view:1") }],
  });
  return null;
}

function press(init: KeyboardEventInit): KeyboardEvent {
  const event = new KeyboardEvent("keydown", { bubbles: true, cancelable: true, ctrlKey: true, ...init });
  window.dispatchEvent(event);
  return event;
}

describe("useGlobalShortcuts", () => {
  it("routes shortcuts to the same intents as the rail and claims the key", async () => {
    const log: string[] = [];
    const view = await mountTestComponent(<Harness log={log} />);
    try {
      let event: KeyboardEvent | null = null;
      await act(async () => { event = press({ key: "k", code: "KeyK" }); });
      await act(async () => { press({ key: ",", code: "Comma" }); });
      await act(async () => { press({ key: "2", code: "Digit2" }); });
      assert.deepEqual(log, ["search", "settings", "view:1"]);
      assert.equal((event as KeyboardEvent | null)?.defaultPrevented, true);
    } finally { await view.cleanup(); }
  });

  it("leaves a digit with no rail entry alone", async () => {
    const log: string[] = [];
    const view = await mountTestComponent(<Harness log={log} />);
    try {
      let event: KeyboardEvent | null = null;
      await act(async () => { event = press({ key: "5", code: "Digit5" }); });
      assert.deepEqual(log, []);
      assert.equal((event as KeyboardEvent | null)?.defaultPrevented, false);
    } finally { await view.cleanup(); }
  });

  it("does nothing while a dialog owns the keyboard", async () => {
    const log: string[] = [];
    const view = await mountTestComponent(<Harness log={log} />);
    try {
      const dialog = document.createElement("div");
      dialog.setAttribute("role", "dialog");
      document.body.append(dialog);
      await act(async () => { press({ key: "1", code: "Digit1" }); });
      dialog.remove();
      await act(async () => { press({ key: "1", code: "Digit1" }); });
      assert.deepEqual(log, ["view:0"]);
    } finally { await view.cleanup(); }
  });

  it("does nothing while disabled", async () => {
    const log: string[] = [];
    const view = await mountTestComponent(<Harness enabled={false} log={log} />);
    try {
      await act(async () => { press({ key: "k", code: "KeyK" }); });
      assert.deepEqual(log, []);
    } finally { await view.cleanup(); }
  });

  it("ignores keys while an IME is composing", async () => {
    const log: string[] = [];
    const view = await mountTestComponent(<Harness log={log} />);
    try {
      await act(async () => { press({ key: "k", code: "KeyK", isComposing: true }); });
      assert.deepEqual(log, []);
    } finally { await view.cleanup(); }
  });
});
