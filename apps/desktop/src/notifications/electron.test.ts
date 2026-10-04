import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { runInNewContext } from "node:vm";
import * as path from "node:path";
import ts from "typescript";
import type { IpcMain, NotificationConstructorOptions } from "electron";
import type { BridgeEvent } from "@yinfengwindy/shiori-sdk/contract";
import { DesktopMessageNotifications } from "./controller.js";
import { notificationChannels } from "./contract.js";
import { NotificationActivation } from "./activation.js";
import { windowsNotificationToast } from "./windowsToast.js";
import { windowsNotificationIdentity } from "./windowsIdentity.js";
import type { createDesktopMessageNotifications } from "./electron.js";

async function harness(options: { windows?: boolean; registrationError?: Error } = {}) {
  const notifications: NativeNotification[] = [];
  const logs: unknown[] = [];
  const sent: string[] = [];
  let visible = true;
  let focused = false;
  let minimized = false;
  let shown = 0;
  let nativeError: Error | null = null;
  let supported = true;
  let registered = false;
  const sender = { send: (channel: string) => { sent.push(channel); } };
  const window = {
    webContents: sender, isDestroyed: () => false,
    isVisible: () => visible, isFocused: () => focused, isMinimized: () => minimized,
  };
  class NativeNotification extends EventEmitter {
    constructor(readonly options: NotificationConstructorOptions) {
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
        app: { getPath: () => "C:\\AppData" }, shell: {},
        Notification: NativeNotification,
        ipcMain: { handle: (channel: string, listener: Parameters<IpcMain["handle"]>[1]) => handlers.set(channel, listener), removeHandler: (channel: string) => handlers.delete(channel) },
      };
      if (name === "../diagnostics.js") return { logDesktopDiagnostic: (payload: unknown) => logs.push(payload) };
      if (name === "node:path") return path;
      if (name === "../paths.js") return { desktopNotificationIcon: "C:\\Shiori\\assets\\shiori-app-icon.png" };
      if (name === "./controller.js") return { DesktopMessageNotifications };
      if (name === "./windowsToast.js") return { windowsNotificationToast };
      if (name === "./windowsRegistration.js") return { registerWindowsNotifications: () => {
        if (options.registrationError) throw options.registrationError;
        registered = true;
      } };
      if (name === "./contract.js") return { notificationChannels };
      throw new Error(`unexpected import: ${name}`);
    },
  });
  const identity = options.windows ? windowsNotificationIdentity({
    packaged: true, appPath: "C:\\Shiori\\app.asar", userDataPath: "C:\\profile",
    executablePath: "C:\\Shiori\\Shiori.exe", iconPath: "C:\\Shiori\\assets\\shiori-app-icon.png",
  }) : null;
  const activation = new NotificationActivation(identity?.protocol ?? null, () => {
    shown += 1;
    sender.send(notificationChannels.clicked);
  });
  activation.markReady();
  const controller = exports.createDesktopMessageNotifications({
    getWindow: () => window as unknown as ReturnType<Parameters<typeof createDesktopMessageNotifications>[0]["getWindow"]>,
    activation,
    windowsIdentity: identity,
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
    controller, notifications, logs, sent, emit, invoke, activation, registered: () => registered, shown: () => shown,
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

test("Windows toast opens its encoded role through process activation after the native object is dismissed", async () => {
  const h = await harness({ windows: true });
  try {
    h.emit();
    assert.equal(h.registered(), true);
    const notification = h.notifications[0]!;
    const xml = notification.options.toastXml!;
    assert.ok(xml.includes('activationType="protocol"'));
    const launch = /launch="([^"]+)"/.exec(xml)![1]!;
    notification.emit("close");
    assert.equal(h.activation.handleArguments(["C:\\Shiori\\Shiori.exe", launch]), true);
    assert.equal(h.shown(), 1);
    const pending = await h.invoke(notificationChannels.pending) as { roleId: string };
    assert.equal(pending.roleId, "mira");
  } finally { h.controller.dispose(); }
});

test("a failed Windows registration logs the error and suppresses broken notifications", async () => {
  const h = await harness({ windows: true, registrationError: new Error("registry denied") });
  try {
    assert.doesNotThrow(h.emit);
    assert.equal(h.notifications.length, 0);
    assert.equal(h.logs.length, 1);
  } finally { h.controller.dispose(); }
});
