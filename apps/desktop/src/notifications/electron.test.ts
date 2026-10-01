import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { runInNewContext } from "node:vm";
import ts from "typescript";
import type { IpcMain } from "electron";
import type { BridgeEvent } from "@shiori/sdk/contract";
import { DesktopMessageNotifications } from "./controller.js";
import { notificationChannels } from "./contract.js";
import { NotificationNavigation } from "./navigation.js";
import type { createDesktopMessageNotifications } from "./electron.js";

async function harness() {
  const notifications: NativeNotification[] = [];
  const logs: unknown[] = [];
  const sent: string[] = [];
  let visible = true;
  let focused = false;
  let minimized = false;
  let shown = 0;
  let nativeError: Error | null = null;
  let supported = true;
  const sender = { send: (channel: string) => { sent.push(channel); } };
  const window = {
    webContents: sender, isDestroyed: () => false,
    isVisible: () => visible, isFocused: () => focused, isMinimized: () => minimized,
  };
  class NativeNotification extends EventEmitter {
    constructor(readonly options: { title: string; body: string }) {
      super();
      notifications.push(this);
    }
    static isSupported() { return supported; }
    show() { if (nativeError) throw nativeError; }
    close() { this.emit("close"); }
  }
  const handlers = new Map<string, Parameters<IpcMain["handle"]>[1]>();
  const source = await readFile(new URL("./electron.ts", import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } });
  const exports = {} as { createDesktopMessageNotifications: typeof createDesktopMessageNotifications };
  runInNewContext(compiled.outputText, {
    exports,
    require: (name: string) => {
      if (name === "electron") return {
        Notification: NativeNotification,
        ipcMain: { handle: (channel: string, listener: Parameters<IpcMain["handle"]>[1]) => handlers.set(channel, listener), removeHandler: (channel: string) => handlers.delete(channel) },
      };
      if (name === "../diagnostics.js") return { logDesktopDiagnostic: (payload: unknown) => logs.push(payload) };
      if (name === "./controller.js") return { DesktopMessageNotifications };
      if (name === "./navigation.js") return { NotificationNavigation };
      if (name === "./contract.js") return { notificationChannels };
      throw new Error(`unexpected import: ${name}`);
    },
  });
  const controller = exports.createDesktopMessageNotifications({
    getWindow: () => window as unknown as ReturnType<Parameters<typeof createDesktopMessageNotifications>[0]["getWindow"]>,
    showWindow: () => {
      shown += 1;
      return window as unknown as ReturnType<Parameters<typeof createDesktopMessageNotifications>[0]["showWindow"]>;
    },
  });
  let nextMessageId = 0;
  function emit() {
    const event: BridgeEvent = {
      id: "turn", type: "event", method: "session.updated",
      payload: {
        change: "message_appended", session: { key: "role:mira", metadata: { role_name: "米拉" } },
        message: { id: String(++nextMessageId), role: "assistant", content: "hello" },
      },
    };
    controller.handleEvent(event);
  }
  function invoke(channel: string, value?: unknown, fromMain = true) {
    return handlers.get(channel)!({ sender: fromMain ? sender : {} } as Parameters<Parameters<IpcMain["handle"]>[1]>[0], value);
  }
  return {
    controller, notifications, logs, sent, emit, invoke, shown: () => shown,
    setWindow: (state: { visible: boolean; focused: boolean; minimized: boolean }) => {
      visible = state.visible; focused = state.focused; minimized = state.minimized;
    },
    failNative: (error: Error) => { nativeError = error; },
    unsupported: () => { supported = false; },
  };
}

test("native adapter alerts for hidden, minimized or unfocused main windows only", async () => {
  const h = await harness();
  try {
    h.setWindow({ visible: true, focused: true, minimized: false });
    h.emit();
    assert.equal(h.notifications.length, 0);
    for (const state of [
      { visible: false, focused: true, minimized: false },
      { visible: true, focused: true, minimized: true },
      { visible: true, focused: false, minimized: false },
    ]) {
      h.setWindow(state);
      h.emit();
    }
    assert.equal(h.notifications.length, 3);
    h.unsupported();
    h.emit();
    assert.equal(h.notifications.length, 3);
  } finally { h.controller.dispose(); }
});

test("click reveals the main window and survives an unavailable renderer; other windows cannot consume it", async () => {
  const h = await harness();
  try {
    h.emit();
    h.notifications[0]!.emit("click");
    assert.equal(h.shown(), 1);
    assert.deepEqual(h.sent, [notificationChannels.clicked]);
    const pending = await h.invoke(notificationChannels.pending) as { id: number; roleId: string };
    assert.equal(pending.roleId, "mira");
    assert.equal(await h.invoke(notificationChannels.pending, undefined, false), null);
    await h.invoke(notificationChannels.acknowledge, pending.id, false);
    assert.equal(await h.invoke(notificationChannels.pending), pending);
    await h.invoke(notificationChannels.acknowledge, pending.id);
    assert.equal(await h.invoke(notificationChannels.pending), null);
  } finally { h.controller.dispose(); }
});

test("synchronous and asynchronous native failures are logged without escaping bridge handling", async () => {
  const h = await harness();
  try {
    h.emit();
    h.notifications[0]!.emit("failed", {}, "OS blocked toast");
    h.failNative(new Error("native unavailable"));
    assert.doesNotThrow(h.emit);
    assert.equal(h.logs.length, 2);
  } finally { h.controller.dispose(); }
});
