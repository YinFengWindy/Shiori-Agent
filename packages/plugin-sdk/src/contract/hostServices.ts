import type { RoleRecord } from "../domain/role";
import type { BridgeEvent } from "../rpc";
import type { PluginHostFeedback } from "./feedback";
import type { NativeFilePickerOptions } from "./filePicker";
import type { PluginHostUi } from "./hostUi";

/**
 * One plugin's config values: its `[plugins.<id>]` table as stored, with the
 * schema's defaults filled in. A `${NAME}` environment reference arrives as
 * written, never as the secret it resolves to.
 */
export type PluginConfigValues = Record<string, unknown>;

/**
 * `host.config` (runtime API 2.10.0): the plugin's own config, bound to the
 * plugin when the host mounts it — a plugin can neither name nor reach
 * another plugin's config.
 */
export type PluginHostConfig = {
  /** Reads the current values. */
  get: () => Promise<PluginConfigValues>;
  /**
   * Merges `patch` over the current top-level values and saves the result;
   * resolves to the values as stored. Saves of one plugin run one at a time,
   * each over the values the previous one stored. A value the config schema
   * rejects fails the save with a `PluginBridgeError` and stores nothing.
   */
  save: (patch: PluginConfigValues) => Promise<PluginConfigValues>;
  /**
   * Calls `listener` with the stored values after every successful save of
   * this plugin's config — through `save` or through the plugin's page in
   * 设置 › 插件. Returns the unsubscribe function.
   */
  subscribe: (listener: (values: PluginConfigValues) => void) => () => void;
};

/** `host.assets` (runtime API 2.10.0): displaying local files the host handed to the plugin. */
export type PluginHostAssets = {
  /**
   * Turns a local path the host handed out (in a bridge or RPC response) into
   * a URL for `<img src>` and CSS, exactly as the host renders its own images.
   * A path the host granted no access to yields the host's placeholder URL
   * rather than throwing. Unlike the background `ctx.assets.url`, which
   * answers `null` for such a path so a plugin can decide not to show it,
   * this always returns something an element can render.
   *
   * `url` does not depend on `this` and keeps one identity while the plugin
   * is loaded, so it may be passed on as a bare function (a hook argument or
   * an effect dependency, as the story plugin does) without re-binding.
   */
  url: (path: string) => string;
};

/**
 * Narrow host services available to plugin UI without exposing raw IPC: the
 * injected `host` prop of every bound plugin component, also readable
 * anywhere below it through `usePluginHostServices()`.
 */
export type PluginHostServices = {
  /** Subscribes to every desktop bridge event; returns the unsubscribe function. */
  onEvent: (listener: (event: BridgeEvent) => void) => () => void;
  listRoles: () => Promise<RoleRecord[]>;
  pickImages: (options: { multiple: boolean }) => Promise<string[]>;
  /** Native user selection plus bounded private staging, without a media grant. */
  pickFiles: (options: NativeFilePickerOptions) => Promise<string[]>;
  /** Toasts in the host queue; `persona` (true or a scene key) lets 吟风 front one (runtime API 2.4.0). */
  feedback: PluginHostFeedback;
  /** Host components (runtime API 2.4.0). */
  ui: PluginHostUi;
  /** This plugin's own config (runtime API 2.10.0). */
  config: PluginHostConfig;
  /** Local file URLs (runtime API 2.10.0). */
  assets: PluginHostAssets;
};
