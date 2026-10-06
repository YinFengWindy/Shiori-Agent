import assert from "node:assert/strict";
import { test } from "node:test";
import { PluginGlobalKeys, type KeyboardHook } from "./globalKeys";
import { UiohookKey } from "./hotkey";

test("multiple plugins share one hook and replacement releases a held registration", () => {
  const listeners = new Map<string, (event: { keycode: number; ctrlKey: boolean; altKey: boolean; shiftKey: boolean; metaKey: boolean }) => void>();
  let starts = 0; let stops = 0;
  const hook: KeyboardHook = { on: (name, listener) => listeners.set(name, listener), off: (name) => listeners.delete(name), start: () => { starts++; }, stop: () => { stops++; } };
  const keys = new PluginGlobalKeys(() => hook); const calls: string[] = [];
  keys.register("one", "talk", "Ctrl+Space", (phase) => calls.push(`one:${phase}`));
  keys.register("two", "talk", "Ctrl+Space", (phase) => calls.push(`two:${phase}`));
  const event = { keycode: UiohookKey.Space, ctrlKey: true, altKey: false, shiftKey: false, metaKey: false };
  listeners.get("keydown")!(event); listeners.get("keydown")!(event);
  assert.deepEqual(calls, ["one:down", "two:down"]);
  keys.register("one", "talk", "Alt+Space", (phase) => calls.push(`changed:${phase}`));
  assert.equal(calls.at(-1), "one:up");
  keys.release("one"); assert.equal(stops, 0);
  listeners.get("keyup")!(event); assert.equal(calls.at(-1), "two:up");
  keys.release("two"); assert.equal(starts, 1); assert.equal(stops, 1); assert.equal(listeners.size, 0);
});
