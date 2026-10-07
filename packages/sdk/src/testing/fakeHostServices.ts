import type { RoleRecord } from "../domain/role";
import type { FeedbackTone, PluginFeedbackOptions, PluginHostFeedback } from "../contract/feedback";
import type { NativeFilePathPickerOptions, NativeFilePickerOptions } from "../contract/filePicker";
import type { PluginConfigValues, PluginHostServices } from "../contract/hostServices";
import type { BridgeEvent } from "../rpc";
import { createFakeHostUi } from "./fakeHostUi";

/** One call a plugin made on the fake host services, in call order. */
export type FakeHostCall =
  | { service: "onEvent" }
  | { service: "listRoles" }
  | { service: "pickImages"; options: { multiple: boolean } }
  | { service: "pickFiles"; options: NativeFilePickerOptions }
  | { service: "pickFilePaths"; options: NativeFilePathPickerOptions }
  | { service: "pickDirectory" }
  | { service: "feedback"; tone: FeedbackTone; message: string; options?: PluginFeedbackOptions }
  | { service: "config.get" }
  | { service: "config.save"; patch: PluginConfigValues }
  | { service: "assets.url"; path: string };

/** A recorded `host.feedback` toast. */
export type FakeHostFeedback = Extract<FakeHostCall, { service: "feedback" }>;

/** Answers of the fake host services; every call is recorded whether answered by default or here. */
export type FakeHostServicesOptions = {
  /** `listRoles`; default no roles. */
  listRoles?: () => Promise<RoleRecord[]>;
  /** `pickImages`; default the user picks nothing. */
  pickImages?: PluginHostServices["pickImages"];
  /** `pickFiles`; default the user picks nothing. */
  pickFiles?: PluginHostServices["pickFiles"];
  /** `pickFilePaths`; default the user picks nothing. */
  pickFilePaths?: PluginHostServices["pickFilePaths"];
  /** `pickDirectory`; default the user cancels (`null`). */
  pickDirectory?: PluginHostServices["pickDirectory"];
  /** The plugin's stored config before the test; default empty. */
  config?: PluginConfigValues;
  /**
   * Replaces the in-memory save (which merges `patch` over `current`), e.g.
   * to reject or hold it; resolves to the values to store.
   */
  saveConfig?: (patch: PluginConfigValues, current: PluginConfigValues) => Promise<PluginConfigValues>;
  /** `assets.url`; default `fake-asset://<path>`. */
  assetUrl?: (path: string) => string;
};

/**
 * In-memory host services for plugin tests: pass `host` as the injected
 * prop or to `PluginHostServicesProvider`, then assert on `calls` (every
 * service call in order), `feedback` (the toasts), `uiRenders` (the props of
 * each `host.ui` render) and `config()` (the stored config). `emit` delivers
 * a bridge event to `onEvent` listeners.
 */
export function createFakeHostServices(options: FakeHostServicesOptions = {}) {
  const calls: FakeHostCall[] = [];
  const eventListeners = new Set<(event: BridgeEvent) => void>();
  const configListeners = new Set<(values: PluginConfigValues) => void>();
  let storedConfig: PluginConfigValues = { ...options.config };
  const { ui, renders, accountDetailActionsZone } = createFakeHostUi();

  const toast = (tone: FeedbackTone) => (message: string, toastOptions?: PluginFeedbackOptions) => {
    calls.push({ service: "feedback", tone, message, options: toastOptions });
  };
  const feedback: PluginHostFeedback = { success: toast("success"), info: toast("info"), warning: toast("warning"), error: toast("error") };

  const host: PluginHostServices = {
    onEvent(listener) {
      calls.push({ service: "onEvent" });
      eventListeners.add(listener);
      return () => { eventListeners.delete(listener); };
    },
    listRoles() {
      calls.push({ service: "listRoles" });
      return options.listRoles ? options.listRoles() : Promise.resolve([]);
    },
    pickImages(pickOptions) {
      calls.push({ service: "pickImages", options: pickOptions });
      return options.pickImages ? options.pickImages(pickOptions) : Promise.resolve([]);
    },
    pickFiles(pickOptions) {
      calls.push({ service: "pickFiles", options: pickOptions });
      return options.pickFiles ? options.pickFiles(pickOptions) : Promise.resolve([]);
    },
    pickFilePaths(pickOptions) {
      calls.push({ service: "pickFilePaths", options: pickOptions });
      return options.pickFilePaths ? options.pickFilePaths(pickOptions) : Promise.resolve([]);
    },
    pickDirectory() {
      calls.push({ service: "pickDirectory" });
      return options.pickDirectory ? options.pickDirectory() : Promise.resolve(null);
    },
    feedback,
    ui,
    config: {
      async get() {
        calls.push({ service: "config.get" });
        return { ...storedConfig };
      },
      async save(patch) {
        calls.push({ service: "config.save", patch });
        const current = { ...storedConfig };
        storedConfig = options.saveConfig ? { ...await options.saveConfig(patch, current) } : { ...current, ...patch };
        for (const listener of [...configListeners]) listener({ ...storedConfig });
        return { ...storedConfig };
      },
      subscribe(listener) {
        configListeners.add(listener);
        return () => { configListeners.delete(listener); };
      },
    },
    assets: {
      url(path) {
        calls.push({ service: "assets.url", path });
        return options.assetUrl ? options.assetUrl(path) : `fake-asset://${path}`;
      },
    },
  };

  return {
    host,
    calls,
    /** The `host.feedback` toasts, in order. */
    get feedback() { return calls.filter((call): call is FakeHostFeedback => call.service === "feedback"); },
    uiRenders: renders,
    /** Where `host.ui.AccountDetailActions` render (the host's account dialog danger zone). */
    accountDetailActionsZone,
    /** The plugin's stored config now. */
    config: () => ({ ...storedConfig }),
    /** Delivers `event` to every `host.onEvent` listener. */
    emit(event: BridgeEvent) {
      for (const listener of [...eventListeners]) listener(event);
    },
  };
}

/** What `createFakeHostServices` returns. */
export type FakeHostServices = ReturnType<typeof createFakeHostServices>;
