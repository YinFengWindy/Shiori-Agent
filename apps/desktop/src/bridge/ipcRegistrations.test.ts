import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { BrowserWindow, WebContents } from "electron";
import { PluginUiResources } from "../plugins/uiResources.js";
import {
  registerDesktopIpcHandlers,
  type DesktopIpcHost,
  type RegisterDesktopIpcOptions,
} from "./ipcRegistrations.js";

type WindowCall = { window: string; method: string };

/** A window double that records which window each handler acted on. */
class FakeWindow {
  readonly webContents = {} as WebContents;
  constructor(readonly label: string, private readonly calls: WindowCall[], private readonly maximized = false) {}
  minimize() { this.calls.push({ window: this.label, method: "minimize" }); }
  maximize() { this.calls.push({ window: this.label, method: "maximize" }); }
  unmaximize() { this.calls.push({ window: this.label, method: "unmaximize" }); }
  close() { this.calls.push({ window: this.label, method: "close" }); }
  isMaximized() { return this.maximized; }
  isVisible() { return true; }
  asBrowserWindow() { return this as unknown as BrowserWindow; }
}

function setup(overrides: {
  petWindowLabel?: string;
  invoke?: RegisterDesktopIpcOptions["bridge"]["invoke"];
  showOpenDialog?: DesktopIpcHost["showOpenDialog"];
  pluginUiResources?: PluginUiResources;
} = {}) {
  const windowCalls: WindowCall[] = [];
  const petCalls: Array<{ method: string; args: unknown[] }> = [];
  const observationCalls: string[] = [];
  const externalOpened: string[] = [];
  const handlers = new Map<string, (event: never, ...args: never[]) => unknown>();
  const listeners = new Map<string, (event: never, ...args: never[]) => void>();

  const main = new FakeWindow("main", windowCalls, true);
  const other = new FakeWindow("other", windowCalls);
  const pet = new FakeWindow("pet", windowCalls);
  const bySender = new Map<WebContents, FakeWindow>([
    [main.webContents, main],
    [other.webContents, other],
    [pet.webContents, pet],
  ]);
  const petWindowLabel = overrides.petWindowLabel ?? "pet";

  const host = {
    handle: (channel: string, listener: unknown) => {
      handlers.set(channel, listener as (event: never, ...args: never[]) => unknown);
    },
    on: (channel: string, listener: unknown) => {
      listeners.set(channel, listener as (event: never, ...args: never[]) => void);
    },
    windowFromWebContents: (sender: WebContents) => bySender.get(sender)?.asBrowserWindow() ?? null,
    showOpenDialog: overrides.showOpenDialog ?? (async () => ({ canceled: true, filePaths: [] })),
    openExternal: async (url: string) => { externalOpened.push(url); },
    logDiagnostic: () => undefined,
    dragFileIcon: "drag-icon.png",
    registerVoiceIpc: () => undefined,
  } as unknown as DesktopIpcHost;

  // Since #181-C there is no pet object in this process: the boundary takes a
  // window predicate and a command sink, both supplied by `main.ts`.
  const isPetWindow = (window: BrowserWindow | null) =>
    Boolean(window) && (window as unknown as FakeWindow).label === petWindowLabel;
  const requestDesktopPetCommand = (command: unknown) => {
    petCalls.push({ method: "command", args: [command] });
  };

  registerDesktopIpcHandlers(host, {
    pluginUiResources: overrides.pluginUiResources,
    bridge: {
      invoke: overrides.invoke ?? (async () => ({ payload: {} })),
      isRunning: () => true,
      getLastError: () => null,
      restart: async () => undefined,
    },
    localAssets: {
      grantTrustedPayload: () => [],
      grantPath: () => null,
      resolveReference: () => null,
    },
    localAssetImportsRoot: "imports",
    openLocalAttachment: async () => ({ ok: true }),
    isPetWindow,
    requestDesktopPetCommand,
    desktopObservation: {
      restore: async () => { observationCalls.push("restore"); },
      dismissBubble: () => { observationCalls.push("dismissBubble"); },
    },
    voiceRecorder: {},
    voiceController: {},
    voicePlayback: {},
  } as unknown as RegisterDesktopIpcOptions);

  return {
    windows: { main, other, pet },
    windowCalls,
    petCalls,
    observationCalls,
    externalOpened,
    channels: { handled: [...handlers.keys()], listened: [...listeners.keys()] },
    async invokeHandler(channel: string, sender: WebContents, ...args: unknown[]) {
      const handler = handlers.get(channel);
      assert.ok(handler, `${channel} should be registered as an invoke handler`);
      return await (handler as (event: unknown, ...rest: unknown[]) => unknown)({ sender }, ...args);
    },
    sendMessage(channel: string, sender: WebContents, ...args: unknown[]) {
      const listener = listeners.get(channel);
      assert.ok(listener, `${channel} should be registered as a message listener`);
      (listener as (event: unknown, ...rest: unknown[]) => void)({ sender }, ...args);
    },
  };
}

describe("desktop ipc window boundaries", () => {
  it("controls the window that sent the request, not an arbitrary one", async () => {
    const ipc = setup();

    await ipc.invokeHandler("desktop:window-control", ipc.windows.other.webContents, "minimize");

    assert.deepEqual(ipc.windowCalls, [{ window: "other", method: "minimize" }]);
  });

  it("unmaximizes only when the requesting window is already maximized", async () => {
    const ipc = setup();

    await ipc.invokeHandler("desktop:window-control", ipc.windows.main.webContents, "toggleMaximize");
    await ipc.invokeHandler("desktop:window-control", ipc.windows.other.webContents, "toggleMaximize");

    assert.deepEqual(ipc.windowCalls, [
      { window: "main", method: "unmaximize" },
      { window: "other", method: "maximize" },
    ]);
  });

  it("reports the state of the requesting window", async () => {
    const ipc = setup();

    const mainState = await ipc.invokeHandler("desktop:window-state", ipc.windows.main.webContents);
    const otherState = await ipc.invokeHandler("desktop:window-state", ipc.windows.other.webContents);

    assert.deepEqual(mainState, { isMaximized: true, isVisible: true });
    assert.deepEqual(otherState, { isMaximized: false, isVisible: true });
  });

  it("reports a closed window as neither maximized nor visible", async () => {
    const ipc = setup();

    const state = await ipc.invokeHandler("desktop:window-state", {} as WebContents);

    assert.deepEqual(state, { isMaximized: false, isVisible: false });
  });
});

it("attaches granted UI URLs to the same roster and serializes admission across windows", async () => {
  const events: string[] = [];
  let unblock!: () => void;
  const gate = new Promise<void>((resolve) => { unblock = resolve; });
  let started!: () => void;
  const admitting = new Promise<void>((resolve) => { started = resolve; });
  let reads = 0;
  const entry = { pluginId: "demo", entry: "shiori-plugin://plugin/token/ui/index.mjs", css: [] };
  class GatedResources extends PluginUiResources {
    override async admit(rows: unknown) {
      events.push(`admit ${reads}`);
      assert.deepEqual(rows, [{ id: "demo", revision: reads }]);
      if (reads === 1) { started(); await gate; }
      return [entry];
    }
  }
  const ipc = setup({
    pluginUiResources: new GatedResources("unused"),
    invoke: async ({ method }) => {
      reads += 1;
      events.push(`read ${reads}`);
      return { id: "request", type: "response", method, error: null, payload: { plugins: [{ id: "demo", revision: reads }] } };
    },
  });
  const first = ipc.invokeHandler("desktop:invoke", ipc.windows.main.webContents, { method: "plugins.list", payload: {} });
  await admitting;
  const second = ipc.invokeHandler("desktop:invoke", ipc.windows.other.webContents, { method: "plugins.list", payload: {} });
  assert.equal(reads, 1);
  unblock();
  const [result] = await Promise.all([first, second]);
  assert.deepEqual(events, ["read 1", "admit 1", "read 2", "admit 2"]);
  assert.deepEqual(result, { assets: [], value: { id: "request", type: "response", method: "plugins.list", error: null, payload: { plugins: [{ id: "demo", revision: 1, renderer_ui: entry }] } } });
});

describe("desktop ipc permission boundaries", () => {
  it("refuses observation methods over the generic renderer bridge", async () => {
    const forwarded: string[] = [];
    const ipc = setup({
      invoke: (async (request: { method: string }) => {
        forwarded.push(request.method);
        return { payload: {} };
      }) as unknown as RegisterDesktopIpcOptions["bridge"]["invoke"],
    });

    await assert.rejects(
      () => ipc.invokeHandler("desktop:invoke", ipc.windows.main.webContents, {
        method: "observation.start",
        payload: {},
      }),
      /observation bridge methods are restricted to the main process/,
    );
    assert.deepEqual(forwarded, [], "the rejected request must never reach the python bridge");

    await ipc.invokeHandler("desktop:invoke", ipc.windows.main.webContents, {
      method: "roles.list",
      payload: {},
    });
    assert.deepEqual(forwarded, ["roles.list"]);
  });

  it("exposes bubble dismissal as the only pet observation channel", () => {
    const ipc = setup();
    const observationChannels = [...ipc.channels.handled, ...ipc.channels.listened]
      .filter((channel) => channel.includes("observation"));

    assert.deepEqual(observationChannels, ["desktop:pet-observation-dismiss"]);
  });

  it("ignores observation dismissal from a window that is not the pet", async () => {
    const ipc = setup();

    await ipc.invokeHandler("desktop:pet-observation-dismiss", ipc.windows.main.webContents);
    assert.deepEqual(ipc.observationCalls, []);

    await ipc.invokeHandler("desktop:pet-observation-dismiss", ipc.windows.pet.webContents);
    assert.deepEqual(ipc.observationCalls, ["dismissBubble"]);
  });

  it("turns a pet sync request into a command for the plugin that owns the pet", async () => {
    const ipc = setup();

    await ipc.invokeHandler("desktop:pet-sync", ipc.windows.main.webContents, false);
    await ipc.invokeHandler("desktop:pet-sync", ipc.windows.main.webContents);
    await ipc.invokeHandler("desktop:pet-sync", ipc.windows.main.webContents, "not a boolean");

    // Since #181-C the controller lives in the plugin host renderer, so this
    // cannot await the sync — and must not refresh observation on its own
    // either; that happens when the plugin writes its settings back.
    assert.deepEqual(ipc.petCalls, [
      { method: "command", args: [{ kind: "sync", forceVisible: false }] },
      { method: "command", args: [{ kind: "sync", forceVisible: undefined }] },
      { method: "command", args: [{ kind: "sync", forceVisible: undefined }] },
    ]);
    assert.deepEqual(ipc.observationCalls, []);
  });

  it("keeps no pet-specific window channels of its own", () => {
    const ipc = setup();
    const petChannels = [...ipc.channels.handled, ...ipc.channels.listened]
      .filter((channel) => channel.startsWith("desktop:pet-"));

    // Since #181-B the pet's window is a plugin surface: its ready handshake,
    // bubble sizing, drag, double click and context menu arrive on the generic
    // DesktopSurface channels and are attributed there by window identity.
    // What is left here is the pet's *domain* plumbing, not its window.
    assert.deepEqual(petChannels.sort(), [
      "desktop:pet-observation-dismiss",
      "desktop:pet-sync",
    ]);
  });

  it("routes external links through the shared policy before reaching the shell", async () => {
    const ipc = setup();

    const blocked = await ipc.invokeHandler("desktop:open-external", ipc.windows.main.webContents, {
      url: "javascript:alert(1)",
    });
    assert.deepEqual(blocked, { ok: false, error: "external link protocol is not authorized" });
    assert.deepEqual(ipc.externalOpened, [], "a rejected link must never reach shell.openExternal");

    const allowed = await ipc.invokeHandler("desktop:open-external", ipc.windows.main.webContents, {
      url: "https://example.com/docs",
    });
    assert.deepEqual(allowed, { ok: true, error: null });
    assert.deepEqual(ipc.externalOpened, ["https://example.com/docs"]);
  });
});


describe("generic native file picker boundary", () => {
  it("exposes one generic picker and removes the pet-specific endpoint", () => {
    const ipc = setup();
    assert.ok(ipc.channels.handled.includes("desktop:pick-files"));
    assert.ok(!ipc.channels.handled.includes("desktop:pick-pet-package"));
  });
});


it("generic picker IPC forwards validated dialog options and returns cancellation without a media transport", async () => {
  const dialogs: unknown[] = [];
  const ipc = setup({ showOpenDialog: async (options) => {
    dialogs.push(options); return { canceled: true, filePaths: ["/ignored.zip"] };
  } });
  const options = { namespace: "sample", maxFileBytes: 32, multiple: true,
    filters: [{ name: "Archives", extensions: ["zip"] }] };
  assert.deepEqual(await ipc.invokeHandler("desktop:pick-files", ipc.windows.main.webContents, options), []);
  assert.deepEqual(dialogs, [{ properties: ["openFile", "multiSelections"], filters: options.filters }]);
  await assert.rejects(ipc.invokeHandler("desktop:pick-files", ipc.windows.main.webContents, { ...options, source: "/secret.zip" }), /不支持/);
  assert.equal(dialogs.length, 1);
});
