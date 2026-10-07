import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { runInNewContext } from "node:vm";
import ts from "typescript";
import type { BridgeEvent } from "@yinfengwindy/shiori-sdk/contract";
import type { DesktopApi, LocalAssetTransport } from "./bridge/shared";
import { PreloadLocalAssetCache } from "./assets/preloadLocalAssetCache";
import { notificationChannels } from "./notifications/contract";
import { createDesktopEventSubscription } from "./bridge/desktopEventSubscription";

/** Runs the actual preload with a mocked Electron boundary, without launching a desktop. */
async function loadPreload(
  invoke: (channel: string, options: unknown) => Promise<unknown>,
  ipcEvents = new EventEmitter(),
) {
  const source = await readFile(new URL("./preload.ts", import.meta.url), "utf8");
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } });
  const exposed: { api?: DesktopApi } = {};
  const constantModules = new Set(["./assets/localAssetContract.js", "./surface/host.js", "./surface/ipc.js", "./plugins/ipc.js", "./tray/ipc.js"]);
  runInNewContext(compiled.outputText, {
    exports: {}, window: { addEventListener: () => {} },
    require: (name: string) => {
      if (name === "electron") return { ipcRenderer: {
        invoke,
        on: ipcEvents.on.bind(ipcEvents),
        off: ipcEvents.off.bind(ipcEvents),
      }, contextBridge: {
        exposeInMainWorld: (_name: string, api: DesktopApi) => { exposed.api = api; },
      } };
      if (name === "./assets/preloadLocalAssetCache.js") return { PreloadLocalAssetCache };
      if (name === "./bridge/desktopEventSubscription.js") return { createDesktopEventSubscription };
      if (name === "./notifications/contract.js") return { notificationChannels };
      if (constantModules.has(name)) return {};
      throw new Error(`unexpected preload import: ${name}`);
    },
  });
  assert.ok(exposed.api);
  return exposed.api;
}

test("preload exposes generic staged file selection without granting archive media URLs", async () => {
  const calls: unknown[] = [];
  let result: string[] = ["/private/archive.zip"];
  const api = await loadPreload(async (channel, options) => { calls.push({ channel, options }); return result; });
  const options = { namespace: "sample", maxFileBytes: 1024, filters: [{ name: "Archives", extensions: ["zip"] }] };
  assert.deepEqual(await api.pickFiles(options), result);
  assert.deepEqual(calls, [{ channel: "desktop:pick-files", options }]);
  assert.equal("pickPetPackage" in api, false);
  assert.notEqual(api.localAssetUrl(result[0]), result[0]);
  result = [];
  assert.deepEqual(await api.pickFiles(options), []);
  const failing = await loadPreload(async () => { throw new Error("copy failed"); });
  await assert.rejects(failing.pickFiles(options), /copy failed/);
});

test("preload forwards original-path and directory picks without granting media URLs", async () => {
  const calls: unknown[] = [];
  let result: unknown = ["D:/packs/runtime.7z"];
  const api = await loadPreload(async (channel, options) => { calls.push({ channel, options }); return result; });
  const options = { maxFileBytes: 1024, filters: [{ name: "Archives", extensions: ["7z"] }] };
  assert.deepEqual(await api.pickFilePaths(options), ["D:/packs/runtime.7z"]);
  assert.equal(api.localAssetUrl("D:/packs/runtime.7z"), api.localAssetUrl("D:/never-granted.png"));
  result = null;
  assert.equal(await api.pickDirectory(), null);
  assert.deepEqual(calls, [
    { channel: "desktop:pick-file-paths", options },
    { channel: "desktop:pick-directory", options: undefined },
  ]);
});

test("preload exposes only the role export snapshot ID to the native save channel", async () => {
  const calls: unknown[] = [];
  const api = await loadPreload(async (channel, options) => { calls.push({ channel, options }); return { saved: false }; });
  assert.deepEqual(await api.saveRoleCardExport("snapshot"), { saved: false });
  assert.deepEqual(calls, [{ channel: "desktop:save-role-card", options: "snapshot" }]);
});

test("preload reads and acknowledges retained notification targets and removes click listeners", async () => {
  const calls: unknown[] = [];
  const target = { id: 5, roleId: "mira" };
  const ipcEvents = new EventEmitter();
  const api = await loadPreload(async (channel, options) => {
    calls.push({ channel, options });
    return channel === notificationChannels.pending ? target : undefined;
  }, ipcEvents);
  assert.equal(await api.notifications.getPending(), target);
  await api.notifications.acknowledge(target.id);
  let clicked = 0;
  const unsubscribe = api.notifications.onClicked(() => { clicked += 1; });
  ipcEvents.emit(notificationChannels.clicked);
  assert.equal(clicked, 1);
  unsubscribe();
  assert.equal(ipcEvents.listenerCount(notificationChannels.clicked), 0);
  assert.deepEqual(calls, [
    { channel: notificationChannels.pending, options: undefined },
    { channel: notificationChannels.acknowledge, options: 5 },
  ]);
});

test("preload shares one IPC listener across 32 subscriptions without listener warnings", async (t) => {
  const ipcEvents = new EventEmitter();
  const api = await loadPreload(async () => undefined, ipcEvents);
  const warnings: Error[] = [];
  const onWarning = (warning: Error) => { warnings.push(warning); };
  process.on("warning", onWarning);
  t.after(() => process.off("warning", onWarning));

  const unsubscribe = Array.from({ length: 32 }, () => api.onEvent(() => {}));
  t.after(() => unsubscribe.forEach((release) => release()));
  await new Promise<void>((resolve) => setImmediate(resolve));
  assert.deepEqual(warnings.filter((warning) => warning.name === "MaxListenersExceededWarning"), []);
  assert.equal(ipcEvents.listenerCount("desktop:event"), 1);
  unsubscribe.forEach((release) => release());
  assert.equal(ipcEvents.listenerCount("desktop:event"), 0);
});

test("preload consumes each event transport once and exposes its asset to every subscriber", async (t) => {
  const consume = t.mock.method(PreloadLocalAssetCache.prototype, "consume");
  const ipcEvents = new EventEmitter();
  const api = await loadPreload(async () => undefined, ipcEvents);
  const path = "C:\\workspace\\avatar.png";
  const url = "shiori-asset://local/avatar-token";
  const transport: LocalAssetTransport<BridgeEvent> = {
    value: { id: "asset-event", type: "event", method: "role.updated", payload: { path } },
    assets: [{ path, url, kind: "image" }],
  };
  const received: BridgeEvent[] = [];
  const listener = (event: BridgeEvent) => {
    received.push(event);
    assert.equal(api.localAssetUrl(path), url);
  };
  const unsubscribe = Array.from({ length: 3 }, () => api.onEvent(listener));
  ipcEvents.emit("desktop:event", {}, transport);

  assert.equal(consume.mock.callCount(), 1);
  assert.equal(received.length, 3);
  received.forEach((event) => assert.equal(event, transport.value));
  unsubscribe.forEach((release) => release());
});
