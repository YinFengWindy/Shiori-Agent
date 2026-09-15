import { BridgeError, invokeBridgePayload, type DesktopInvoke } from "../shared/bridgeInvoke";
import type { JsonSchema } from "./jsonSchemaForm";

/** Stable error exposed by the plugin bridge client. */
export class PluginBridgeError extends BridgeError {
  constructor(message: string, code: string, details?: Record<string, unknown>) {
    super(message, code, details);
    this.name = "PluginBridgeError";
  }
}

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

/** One row of the plugin management list (`plugins.list`). */
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
  diagnostic: PluginDiagnostic | null;
  hasConfigSchema: boolean;
  /** Whether an active plugin can be replaced without restarting the process. */
  supportsHotUnload: boolean;
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

function invokePluginPayload<T>(invoke: DesktopInvoke, method: string, payload: Record<string, unknown>, options?: { timeoutMs?: number }): Promise<T> {
  return invokeBridgePayload<T>(invoke, method, payload, PluginBridgeError, options);
}

/** Calls the `plugin.config.*` and `plugins.*` management bridge contracts. */
export interface PluginBridgeClient {
  getConfig(pluginId: string): Promise<PluginConfigSnapshot>;
  setConfig(
    pluginId: string,
    values: Record<string, unknown>,
    options: { operationId: string },
  ): Promise<PluginConfigSaveResult>;
  listPlugins(): Promise<PluginSummary[]>;
  setEnabled(
    pluginId: string,
    enabled: boolean,
    options: { operationId: string },
  ): Promise<PluginSetEnabledResult>;
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
        enabled: boolean; state: string; error: string; has_config_schema: boolean; supports_hot_unload: boolean;
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
        hasConfigSchema: item.has_config_schema,
        supportsHotUnload: item.supports_hot_unload,
      }));
    },
    async setEnabled(pluginId, enabled, options) {
      const payload = await invokePluginPayload<{ plugin_id: string; enabled: boolean; generation: number }>(
        resolveInvoke(), "plugins.setEnabled", { plugin_id: pluginId, enabled, operation_id: options.operationId },
      );
      return { pluginId: payload.plugin_id, enabled: payload.enabled, generation: payload.generation };
    },
  };
}

/**
 * Restricted handle injected into plugin-authored UI components (see
 * `pluginUiModuleContract.tsx`). `call` can only reach methods under that
 * plugin's own `plugin.<id>.*` namespace — the namespace prefix is baked in
 * by `createPluginRpcClient`, not supplied by the caller, so a plugin
 * component cannot address another plugin's methods even by mistake.
 */
export type PluginRpcClient = {
  call<T>(method: string, payload?: Record<string, unknown>, options?: { timeoutMs?: number }): Promise<T>;
};

/**
 * Creates a client scoped to one plugin's own `plugin.<id>.*` RPC namespace.
 * `invoke` resolves lazily (only inside `call`, not eagerly at creation
 * time) so building this client — e.g. once per plugin at UI registration —
 * never requires `window.miraDesktop` to already exist, and pure unit tests
 * that never actually invoke a method don't need a DOM/bridge stub either.
 */
export function createPluginRpcClient(pluginId: string, invoke?: DesktopInvoke): PluginRpcClient {
  return {
    async call<T>(method: string, payload: Record<string, unknown> = {}, options?: { timeoutMs?: number }): Promise<T> {
      return invokePluginPayload<T>(invoke ?? window.miraDesktop.invoke, `plugin.${pluginId}.${method}`, payload, options);
    },
  };
}
