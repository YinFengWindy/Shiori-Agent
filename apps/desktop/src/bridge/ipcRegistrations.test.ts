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
    voiceRecorder: {},
    voiceController: {},
    voicePlayback: {},
  } as unknown as RegisterDesktopIpcOptions);

  return {
    windows: { main, other, pet },
    windowCalls,
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
  const uiEntry = { pluginId: "demo", kind: "ui" as const, entry: "shiori-plugin://plugin/token/ui/index.mjs", css: [], activationToken: "activation-token-1" };
  const backgroundEntry = { pluginId: "demo", kind: "background" as const, entry: "shiori-plugin://plugin/token/background/index.mjs", css: [], activationToken: "activation-token-1" };
  class GatedResources extends PluginUiResources {
    override async admit(rows: unknown) {
      events.push(`admit ${reads}`);
      assert.deepEqual(rows, [{ id: "demo", revision: reads }]);
      if (reads === 1) { started(); await gate; }
      return [uiEntry, backgroundEntry];
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
  assert.deepEqual(result, { assets: [], value: { id: "request", type: "response", method: "plugins.list", error: null, payload: { plugins: [{
    id: "demo", revision: 1,
    // Each sibling field is the same admitted grant with its `kind` tag stripped.
    renderer_ui: { pluginId: "demo", entry: "shiori-plugin://plugin/token/ui/index.mjs", css: [], activationToken: "activation-token-1" },
    renderer_background: { pluginId: "demo", entry: "shiori-plugin://plugin/token/background/index.mjs", css: [], activationToken: "activation-token-1" },
    renderer_surface: undefined,
  }] } } });
});

it("notifies onPluginDeactivated for exactly the plugin ids a fresh roster dropped (#262)", async () => {
  const deactivated: string[] = [];
  let roster: Array<{ id: string; enabled: boolean; state: string }> = [
    { id: "alpha", enabled: true, state: "ACTIVE" },
    { id: "beta", enabled: true, state: "ACTIVE" },
  ];
  const handlers = new Map<string, (event: never, ...args: never[]) => unknown>();
  const host = {
    handle: (channel: string, listener: unknown) => { handlers.set(channel, listener as (event: never, ...args: never[]) => unknown); },
    on: () => undefined,
    windowFromWebContents: () => null,
    showOpenDialog: async () => ({ canceled: true, filePaths: [] }),
    openExternal: async () => undefined,
    logDiagnostic: () => undefined,
    dragFileIcon: "drag-icon.png",
    registerVoiceIpc: () => undefined,
  } as unknown as DesktopIpcHost;
  registerDesktopIpcHandlers(host, {
    bridge: {
      invoke: async ({ method }: { method: string }) => ({ id: "request", type: "response", method, error: null, payload: { plugins: roster } }),
      isRunning: () => true, getLastError: () => null, restart: async () => undefined,
    },
    localAssets: { grantTrustedPayload: () => [], grantPath: () => null, resolveReference: () => null },
    localAssetImportsRoot: "imports",
    openLocalAttachment: async () => ({ ok: true }),
    isPetWindow: () => false,
    voiceRecorder: {},
    voiceController: {},
    voicePlayback: {},
    onPluginDeactivated: (pluginId: string) => deactivated.push(pluginId),
  } as unknown as RegisterDesktopIpcOptions);
  const invokeHandler = handlers.get("desktop:invoke") as (event: unknown, ...args: unknown[]) => unknown;

  await invokeHandler({ sender: {} }, { method: "plugins.list", payload: {} });
  assert.deepEqual(deactivated, []);

  // beta disabled, alpha still ACTIVE.
  roster = [
    { id: "alpha", enabled: true, state: "ACTIVE" },
    { id: "beta", enabled: false, state: "DISABLED" },
  ];
  await invokeHandler({ sender: {} }, { method: "plugins.list", payload: {} });
  assert.deepEqual(deactivated, ["beta"]);

  // alpha rolled back by an activation-report failure (#262); beta stays disabled.
  roster = [
    { id: "alpha", enabled: true, state: "FAILED" },
    { id: "beta", enabled: false, state: "DISABLED" },
  ];
  await invokeHandler({ sender: {} }, { method: "plugins.list", payload: {} });
  assert.deepEqual(deactivated, ["beta", "alpha"]);

  // A repeated identical roster must not re-fire for a plugin already gone.
  await invokeHandler({ sender: {} }, { method: "plugins.list", payload: {} });
  assert.deepEqual(deactivated, ["beta", "alpha"]);
});

describe("desktop ipc permission boundaries", () => {
  it("exposes no observation-specific bubble channel", () => {
    const ipc = setup();
    assert.deepEqual([...ipc.channels.handled, ...ipc.channels.listened]
      .filter((channel) => channel.includes("observation")), []);
  });

  it("keeps no pet-specific window channels of its own", () => {
    const ipc = setup();
    const petChannels = [...ipc.channels.handled, ...ipc.channels.listened]
      .filter((channel) => channel.startsWith("desktop:pet-"));

    // Since #181-B the pet's window is a plugin surface: its ready handshake,
    // bubble sizing, drag, double click and context menu arrive on the generic
    // DesktopSurface channels and are attributed there by window identity.
    // What is left here is the pet's *domain* plumbing, not its window.
    assert.deepEqual(petChannels.sort(), []);
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
