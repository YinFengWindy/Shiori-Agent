// Test-only Electron entry: production surface windows, host and IPC without
// starting the unrelated Python bridge or mutating the user's application data.
import { app, BrowserWindow, ipcMain, screen } from "electron";
import { once } from "node:events";
import { DesktopSurfaceHost } from "../../dist/surface/host.js";
import { registerSurfaceIpc, surfaceChannels } from "../../dist/surface/ipc.js";
import { adaptSurfaceWindow, createDesktopSurfaceWindow } from "../../dist/surface/window.js";
import { desktopSurfaceWindowOptions } from "../../dist/surface/contract.js";
import { preloadScript } from "../../dist/paths.js";

app.setPath("userData", process.env.SHIORI_QA_USER_DATA);
void app.whenReady().then(async () => {
const focusWindow = new BrowserWindow({ width: 400, height: 240 });
await focusWindow.loadURL("data:text/html,<title>Surface focus witness</title><p>Focus witness</p>");
focusWindow.show();
focusWindow.focus();
const records = new Map();
const host = new DesktopSurfaceHost({
  createWindow(key, spec) {
    const handle = createDesktopSurfaceWindow(key, spec, { openLocalAttachment() {} });
    const window = BrowserWindow.fromId(handle.id);
    const record = { window, key, initiallyVisible: window.isVisible(), initiallyAlwaysOnTop: window.isAlwaysOnTop(), events: [], readyCount: 0 };
    window.on("ready-to-show", () => record.events.push("paint"));
    window.on("show", () => record.events.push("show"));
    window.on("focus", () => record.events.push("focus"));
    window.on("always-on-top-changed", (_event, value) => record.events.push(`top:${value}`));
    records.set(handle.id, record);
    return handle;
  },
  workAreaFor: () => screen.getPrimaryDisplay().workArea,
  cursorScreenPoint: () => screen.getCursorScreenPoint(),
});
ipcMain.on(surfaceChannels.ready, (event) => {
  const record = records.get(BrowserWindow.fromWebContents(event.sender)?.id);
  if (record) { record.readyCount++; record.events.push("ready"); }
});
registerSurfaceIpc({
  handle: (channel, listener) => ipcMain.handle(channel, listener),
  on: (channel, listener) => ipcMain.on(channel, listener),
  windowIdFromEvent: (event) => BrowserWindow.fromWebContents(event.sender)?.id ?? null,
}, { surfaces: host, onError: (channel, error) => { console.error(channel, error); } });

globalThis.surfaceQa = {
  create(pluginId, spritesheetUrl) {
    const key = { pluginId, surfaceId: "main" };
    host.create(key, { body: { width: 320, height: 240 } }, { x: 100, y: 100 });
    if (spritesheetUrl) host.setState(key, { load: { package: { spritesheetUrl }, state: "idle" } });
    const record = [...records.values()].find((record) => record.key.pluginId === pluginId);
    host.show(key); // The caller's eager show must not bypass renderer readiness.
    return record.window.id;
  },
  snapshot(id) {
    const record = records.get(id);
    return {
      initiallyVisible: record.initiallyVisible,
      initiallyAlwaysOnTop: record.initiallyAlwaysOnTop,
      visible: record.window.isVisible(),
      focused: record.window.isFocused(),
      focusWitness: focusWindow.isFocused(),
      readyCount: record.readyCount,
      events: [...record.events],
      nativeBackgroundColor: record.window.getBackgroundColor(),
      alwaysOnTop: record.window.isAlwaysOnTop(),
    };
  },
  hide(id) { host.hide(records.get(id).key); },
  destroy(id) { host.destroy(records.get(id).key); records.delete(id); },
  async nativePaintGate(cancel) {
    const window = new BrowserWindow(desktopSurfaceWindowOptions({ body: { width: 80, height: 80 } }, preloadScript));
    const handle = adaptSurfaceWindow(window);
    handle.showInactive();
    const beforePaint = window.isVisible();
    if (cancel) handle.hide();
    const painted = once(window, "ready-to-show");
    await window.loadURL("data:text/html,<p>Paint</p>");
    await painted;
    const afterPaint = window.isVisible();
    window.destroy();
    return { beforePaint, afterPaint };
  },
};
});
