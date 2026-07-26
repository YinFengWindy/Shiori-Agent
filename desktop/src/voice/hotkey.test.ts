import assert from "node:assert/strict";
import test from "node:test";
import { UiohookKey, type UiohookKeyboardEvent } from "uiohook-napi";
import { VoiceHotkeyController, parseHotkey } from "./hotkey.js";

class FakeHook {
  private listeners = new Map<string, Set<(event: UiohookKeyboardEvent) => void>>();
  started = 0;
  stopped = 0;

  on(event: "keydown" | "keyup", listener: (event: UiohookKeyboardEvent) => void): this {
    const listeners = this.listeners.get(event) ?? new Set();
    listeners.add(listener);
    this.listeners.set(event, listeners);
    return this;
  }

  off(event: "keydown" | "keyup", listener: (event: UiohookKeyboardEvent) => void): this {
    this.listeners.get(event)?.delete(listener);
    return this;
  }

  start(): void { this.started += 1; }
  stop(): void { this.stopped += 1; }

  emit(event: "keydown" | "keyup", keycode: number, overrides: Partial<UiohookKeyboardEvent> = {}): void {
    const value = {
      type: event === "keydown" ? 4 : 5,
      time: 0,
      keycode,
      ctrlKey: false,
      altKey: false,
      shiftKey: false,
      metaKey: false,
      ...overrides,
    } as UiohookKeyboardEvent;
    this.listeners.get(event)?.forEach((listener) => listener(value));
  }
}

test("parses the default Ctrl+Space accelerator", () => {
  assert.deepEqual(parseHotkey("Ctrl+Space"), {
    keycode: UiohookKey.Space,
    ctrl: true,
    alt: false,
    shift: false,
    meta: false,
  });
  assert.equal(parseHotkey("Ctrl+Unknown"), null);
});

test("starts on matching keydown and releases on matching keyup", () => {
  const hook = new FakeHook();
  const events: string[] = [];
  const controller = new VoiceHotkeyController({
    onPress: () => events.push("press"),
    onRelease: () => events.push("release"),
    onCancel: () => events.push("cancel"),
  }, hook);
  controller.setHotkey("Ctrl+Space");
  assert.equal(controller.start(), true);
  hook.emit("keydown", UiohookKey.Space, { ctrlKey: true });
  hook.emit("keydown", UiohookKey.Space, { ctrlKey: true });
  hook.emit("keyup", UiohookKey.Space, { ctrlKey: true });
  hook.emit("keydown", UiohookKey.Escape);

  assert.deepEqual(events, ["press", "release", "cancel"]);
  controller.stop();
  assert.equal(hook.started, 1);
  assert.equal(hook.stopped, 1);
});

test("changing the hotkey restarts a registered hook and an empty value disables it", () => {
  const hook = new FakeHook();
  const controller = new VoiceHotkeyController({ onPress: () => undefined, onRelease: () => undefined, onCancel: () => undefined }, hook);
  controller.setHotkey("Ctrl+Space");
  controller.start();
  controller.setHotkey("Alt+V");
  assert.equal(hook.started, 2);
  assert.equal(hook.stopped, 1);
  controller.setHotkey("");
  assert.equal(hook.stopped, 2);
  assert.equal(controller.start(), false);
});

test("changing a held hotkey cancels its active gesture", () => {
  const hook = new FakeHook();
  const events: string[] = [];
  const controller = new VoiceHotkeyController({
    onPress: () => events.push("press"),
    onRelease: () => events.push("release"),
    onCancel: () => events.push("cancel"),
  }, hook);
  controller.setHotkey("Ctrl+Space");
  controller.start();
  hook.emit("keydown", UiohookKey.Space, { ctrlKey: true });

  controller.setHotkey("Alt+V");

  assert.deepEqual(events, ["press", "cancel"]);
});
