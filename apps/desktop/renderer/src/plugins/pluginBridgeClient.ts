import { createPluginCommunicationClient, type PluginCommunicationClient } from "./pluginCommunicationClient";
import { invokeBridgePayload, type DesktopInvoke } from "../shared/bridgeInvoke";
import type { JsonSchema } from "./jsonSchemaForm";
import type { RuntimePluginUi } from "../../../src/plugins/uiContract";

import { PluginBridgeError } from "./pluginBridgeError";
export { PluginBridgeError } from "./pluginBridgeError";

export type PluginConfigSnapshot = {
  pluginId: string;
  schema: JsonSchema | null;
  values: Record<string, unknown>;
};

export type PluginConfigSaveResult = {
  pluginId: string;
  values: Record<string, unknown>;
  generation: number;
};

/** One manifest-declared external channel (the `channels:` block of runtime API 2.2). */
export type PluginChannelDeclaration = {
  name: string;
  label: string;
  /** Describes the binding's sole `allow_from` contact. */
  contactLabel: string | null;
  /** Describes the binding's `chat_id`; `chatIdHint` shows its expected format. */
  chatIdLabel: string | null;
  chatIdHint: string | null;
};

/** Wire shape of one channel declaration, shared by `plugins.list` and `channels.list`. */
type PluginChannelDeclarationPayload = {
  name: string;
  label: string;
  contact_label: string | null;
  chat_id_label: string | null;
  chat_id_hint: string | null;
};

/**
 * Where one listed channel stands (`channels.list`):
 * - `active`: registered in the published generation;
 * - `not_configured`: its provider is enabled but contributed no channel, usually missing credentials;
 * - `failed`: construction/start/status failed, or the plugin itself could not activate (`error` says why);
 * - `plugin_disabled`: the providing plugin is disabled in configuration.
 */
export type ChannelState = "active" | "not_configured" | "failed" | "plugin_disabled";

/** Optional live transport health a channel may report through `status()`. */
export type ChannelConnectionStatus = {
  connected: boolean;
  account?: string;
  detail?: string;
};

/** One row of `channels.list`: a declaration joined with its provider and runtime state. */
export type ChannelSummary = PluginChannelDeclaration & {
  /** Null only for the host-owned `desktop` channel; every external channel comes from a plugin. */
  pluginId: string | null;
  pluginEnabled: boolean;
  state: ChannelState;
  error: string;
  status: ChannelConnectionStatus | null;
};

function mapChannelDeclaration(item: PluginChannelDeclarationPayload): PluginChannelDeclaration {
  return {
    name: item.name,
    label: item.label,
    contactLabel: item.contact_label,
    chatIdLabel: item.chat_id_label,
    chatIdHint: item.chat_id_hint,
  };
}

/** One row of the plugin management list (`plugins.list`). */
/** Manifest `category`: which group of 设置 › 插件 a plugin is listed under. */
export type PluginCategory = "feature" | "channel" | "system";

export type PluginSummary = {
  id: string;
  /** Stable identity of this directory candidate, including duplicate IDs. */
  candidateId: string;
  source: "builtin" | "workspace";
  directory: string;
  name: string;
  version: string;
  description: string;
  enabled: boolean;
  canToggle: boolean;
  state: string;
  error: string;
  /** Renderer-stage failure; backend activation status remains independently visible. */
  rendererError?: string;
  /** Main-process granted URLs; never inferred from a renderer-supplied directory. */
  rendererUi?: RuntimePluginUi;
  /** Main-process granted URLs for this plugin's `plugin-host.html` background entry, if declared. */
  rendererBackground?: RuntimePluginUi;
  /** Main-process granted URLs for this plugin's `surface.html` desktop-surface entry, if declared. */
  rendererSurface?: RuntimePluginUi;
  diagnostic: PluginDiagnostic | null;
  hasConfigSchema: boolean;
  /** Manifest capabilities; `channels` marks a plugin that may contribute channels. */
  capabilities: string[];
  /** Static channel declarations, present even while the plugin is inactive. */
  channels: PluginChannelDeclaration[];
  /** Manifest grouping for 设置 › 插件 (`feature` / `channel` / `system`). */
  category: PluginCategory;
  /** Whether an active plugin can be replaced without restarting the process. */
  supportsHotUnload: boolean;
  /**
   * Required `ui`/`background` renderer entries not yet confirmed ready by
   * their owning window. Non-empty only while `state === "ACTIVE"`; a
   * plugin should be presented as still activating, not fully ACTIVE, while
   * this is non-empty (#262 AC1).
   */
  pendingRendererKinds: string[];
  /** Manual trust is bound to the displayed candidate and complete content fingerprint. */
  canTrust?: boolean;
  trustFingerprint?: string | null;
  trustDirectory?: string;
  trustPendingRestart?: boolean;
  /** Approved code changes applied only at the next application startup. */
  pendingOperation?: "install" | "update" | "uninstall";
  pendingVersion?: string;
  /** False for queued installs or failed installs without a code directory. */
  packageInstalled?: boolean;
  /** Retained startup transaction failure, with the prior package restored. */
  packageOperationError?: string;
};

/** Structured static admission or runtime dependency rejection. */
export type PluginDiagnostic = {
  code: string;
  stage: string;
  field: string;
  reason: string;
  path: string;
  state: string;
};

export type PluginSetEnabledResult = {
  pluginId: string;
  enabled: boolean;
  generation: number;
};

/**
 * Outcome a renderer reports for one admitted `renderer.<kind>` entry
 * (#262). `activationToken` is the admitted entry's own
 * `RuntimePluginUi.activationToken` (copied verbatim, not invented by the
 * caller) — the backend rejects a report whose token does not match its
 * current handle for that plugin, which is what makes an abandoned load
 * from a disable/re-enable cycle harmless if it resolves late.
 */
export type PluginActivationOutcome =
  | { ok: true; activationToken: string }
  | { ok: false; reason: string; activationToken: string };

function invokePluginPayload<T>(invoke: DesktopInvoke, method: string, payload: Record<string, unknown>, options?: { timeoutMs?: number }): Promise<T> {
  return invokeBridgePayload<T>(invoke, method, payload, PluginBridgeError, options);
}

/** Calls the `plugin.config.*` and `plugins.*` management bridge contracts. */
export interface PluginBridgeClient {
  trustPlugin(candidateId: string, fingerprint: string): Promise<void>;
  getConfig(pluginId: string): Promise<PluginConfigSnapshot>;
  setConfig(
    pluginId: string,
    values: Record<string, unknown>,
    options: { operationId: string },
  ): Promise<PluginConfigSaveResult>;
  listPlugins(): Promise<PluginSummary[]>;
  /** Lists `desktop`, builtin and plugin-declared channels with their runtime state (`channels.list`). */
  listChannels(): Promise<ChannelSummary[]>;
  setEnabled(
    pluginId: string,
    enabled: boolean,
    options: { operationId: string },
  ): Promise<PluginSetEnabledResult>;
  /**
   * Reports whether this window's admitted `renderer.<kind>` entry for
   * `pluginId` loaded successfully. A failure rolls the whole plugin back on
   * the backend and republishes the roster (#262); a success only clears it
   * from `pendingRendererKinds`. Never throws on its own — a stale or
   * duplicate report for a plugin/kind the backend is not tracking is
   * accepted and simply reported back as `changed: false`.
   */
  reportActivation(
    pluginId: string,
    kind: "ui" | "background" | "surface",
    outcome: PluginActivationOutcome,
  ): Promise<void>;
}

/**
 * Creates the renderer client for the plugin config and management bounded
 * context. `invoke` resolves lazily (inside each call, not eagerly at
 * creation time) for the same reason as `createPluginRpcClient`: building
 * this client must not require `window.miraDesktop` to already exist.
 */
export function createPluginBridgeClient(invoke?: DesktopInvoke): PluginBridgeClient {
  const resolveInvoke = () => invoke ?? window.miraDesktop.invoke;
  return {
    async trustPlugin(candidateId, fingerprint) {
      await invokePluginPayload(resolveInvoke(), "plugins.trust", { candidate_id: candidateId, fingerprint });
    },
    async getConfig(pluginId) {
      const payload = await invokePluginPayload<{ plugin_id: string; schema: JsonSchema | null; values: Record<string, unknown> }>(
        resolveInvoke(), "plugin.config.get", { plugin_id: pluginId },
      );
      return { pluginId: payload.plugin_id, schema: payload.schema, values: payload.values };
    },
    async setConfig(pluginId, values, options) {
      const payload = await invokePluginPayload<{ plugin_id: string; values: Record<string, unknown>; generation: number }>(
        resolveInvoke(), "plugin.config.set", { plugin_id: pluginId, values, operation_id: options.operationId },
      );
      return { pluginId: payload.plugin_id, values: payload.values, generation: payload.generation };
    },
    async listPlugins() {
      const payload = await invokePluginPayload<{ plugins: Array<{
        id: string; name: string; version: string; description: string;
        candidate_id: string; source: "builtin" | "workspace"; directory: string;
        can_toggle: boolean; diagnostic: PluginDiagnostic | null;
        renderer_ui?: RuntimePluginUi;
        renderer_background?: RuntimePluginUi;
        renderer_surface?: RuntimePluginUi;
        can_trust?: boolean; trust_fingerprint?: string | null; trust_directory?: string; trust_pending_restart?: boolean;
        enabled: boolean; state: string; error: string; has_config_schema: boolean; supports_hot_unload: boolean;
        pending_renderer_kinds?: string[];
        capabilities: string[]; channels: PluginChannelDeclarationPayload[]; category: PluginCategory;
        package_installed?: boolean; pending_operation?: PluginSummary["pendingOperation"]; pending_version?: string; package_operation_error?: string;
      }> }>(resolveInvoke(), "plugins.list", {});
      return payload.plugins.map((item) => ({
        id: item.id,
        candidateId: item.candidate_id,
        source: item.source,
        directory: item.directory,
        name: item.name,
        version: item.version,
        description: item.description,
        enabled: item.enabled,
        canToggle: item.can_toggle,
        state: item.state,
        error: item.error,
        diagnostic: item.diagnostic,
        rendererUi: item.renderer_ui,
        rendererBackground: item.renderer_background,
        rendererSurface: item.renderer_surface,
        canTrust: item.can_trust,
        trustFingerprint: item.trust_fingerprint,
        trustDirectory: item.trust_directory,
        trustPendingRestart: item.trust_pending_restart,
        pendingOperation: item.pending_operation,
        pendingVersion: item.pending_version,
        packageInstalled: item.package_installed,
        packageOperationError: item.package_operation_error,
        hasConfigSchema: item.has_config_schema,
        capabilities: item.capabilities,
        channels: item.channels.map(mapChannelDeclaration),
        category: item.category,
        supportsHotUnload: item.supports_hot_unload,
        pendingRendererKinds: item.pending_renderer_kinds ?? [],
      }));
    },
    async listChannels() {
      const payload = await invokePluginPayload<{ channels: Array<PluginChannelDeclarationPayload & {
        plugin_id: string | null; plugin_enabled: boolean; state: ChannelState; error: string;
        status: ChannelConnectionStatus | null;
      }> }>(resolveInvoke(), "channels.list", {});
      return payload.channels.map((item) => ({
        ...mapChannelDeclaration(item),
        pluginId: item.plugin_id,
        pluginEnabled: item.plugin_enabled,
        state: item.state,
        error: item.error,
        status: item.status,
      }));
    },
    async setEnabled(pluginId, enabled, options) {
      const payload = await invokePluginPayload<{ plugin_id: string; enabled: boolean; generation: number }>(
        resolveInvoke(), "plugins.setEnabled", { plugin_id: pluginId, enabled, operation_id: options.operationId },
      );
      return { pluginId: payload.plugin_id, enabled: payload.enabled, generation: payload.generation };
    },
    async reportActivation(pluginId, kind, outcome) {
      await invokePluginPayload(resolveInvoke(), "plugins.activation.report", {
        plugin_id: pluginId,
        kind,
        ok: outcome.ok,
        activation_token: outcome.activationToken,
        ...(outcome.ok ? {} : { reason: outcome.reason }),
      });
    },
  };
}

/** Namespace-bound calls, events, declared peers and background requests. */
export type PluginRpcClient = PluginCommunicationClient;

/** Creates a lazy, disposable plugin communication context. */
export function createPluginRpcClient(pluginId: string, invoke?: DesktopInvoke): PluginRpcClient {
  return createPluginCommunicationClient(pluginId, { invoke });
}
