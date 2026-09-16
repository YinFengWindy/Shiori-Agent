import { createPluginRpcClient } from "./pluginBridgeClient";
import { pluginRoleSettingsRegistry, type PluginRoleValues } from "./pluginFeatureRegistry";
import { isPluginEnabled } from "./pluginEnabledStateStore";

/** All plugin-owned role drafts, keyed by the contributing plugin id. */
export type PluginRoleSettingsDraft = Record<string, PluginRoleValues>;

/** Hydrates runtime-backed drafts and independent plugin projections. */
export function readPluginRoleSettings(runtimeConfig: Record<string, unknown> = {}, pluginState: PluginRoleSettingsDraft = {}): PluginRoleSettingsDraft {
  return Object.fromEntries(pluginRoleSettingsRegistry.list()
    .filter((entry) => entry.storage !== "plugin" || pluginState[entry.pluginId] !== undefined)
    .map((entry) => [entry.pluginId, entry.read(entry.storage === "plugin" ? pluginState[entry.pluginId] : runtimeConfig)]));
}

/** Writes only runtime-backed contributions into runtime_config. */
export function writePluginRoleSettings(runtimeConfig: Record<string, unknown>, drafts: PluginRoleSettingsDraft) {
  return pluginRoleSettingsRegistry.list().reduce((current, entry) => (
    entry.storage !== "plugin" && drafts[entry.pluginId] ? entry.write(current, drafts[entry.pluginId]) : current
  ), runtimeConfig);
}

/** Includes changed active independent drafts in the same roles.update transaction. */
export function buildPluginRoleDraftUpdates(drafts: PluginRoleSettingsDraft, pluginState: PluginRoleSettingsDraft = {}) {
  return Object.fromEntries(pluginRoleSettingsRegistry.list()
    .filter((entry) => entry.storage === "plugin" && isPluginEnabled(entry.pluginId)
      && drafts[entry.pluginId] !== undefined
      && JSON.stringify(drafts[entry.pluginId]) !== JSON.stringify(entry.read(pluginState[entry.pluginId] ?? {})))
    .map((entry) => [entry.pluginId, drafts[entry.pluginId]]));
}

/** Invokes plugin-owned post-save effects only after persistence succeeds. */
export async function notifyPluginRoleSaved(drafts: PluginRoleSettingsDraft, previousRuntime: Record<string, unknown> = {}, previousState: PluginRoleSettingsDraft = {}) {
  const previous = readPluginRoleSettings(previousRuntime, previousState);
  await Promise.all(pluginRoleSettingsRegistry.list().filter((entry) => isPluginEnabled(entry.pluginId)
    && drafts[entry.pluginId] !== undefined
    && JSON.stringify(drafts[entry.pluginId]) !== JSON.stringify(previous[entry.pluginId]))
    .map(async (entry) => {
      if (!entry.afterSave) return;
      const client = createPluginRpcClient(entry.pluginId);
      try { await entry.afterSave(drafts[entry.pluginId], client); }
      finally { await client.dispose(); }
    }));
}

/** Compares drafts with their actual owner, excluding inactive independent state. */
export function pluginRoleSettingsDirty(drafts: PluginRoleSettingsDraft, runtimeConfig: Record<string, unknown> = {}, pluginState: PluginRoleSettingsDraft = {}) {
  const persisted = readPluginRoleSettings(runtimeConfig, pluginState);
  return pluginRoleSettingsRegistry.list().some((entry) => (
    (entry.storage !== "plugin" || isPluginEnabled(entry.pluginId))
    && drafts[entry.pluginId] !== undefined
    && JSON.stringify(drafts[entry.pluginId]) !== JSON.stringify(persisted[entry.pluginId])
  ));
}

/** Replaces independent projections after plugin mutations while retaining other unsaved edits. */
export function refreshPluginRoleDrafts(drafts: PluginRoleSettingsDraft, snapshot: PluginRoleSettingsDraft = {}, expected?: PluginRoleSettingsDraft) {
  const hydrated = { ...drafts };
  for (const entry of pluginRoleSettingsRegistry.list()) {
    if (entry.storage === "plugin" && snapshot[entry.pluginId] !== undefined
      && (expected === undefined || drafts[entry.pluginId] === undefined
        || JSON.stringify(drafts[entry.pluginId]) === JSON.stringify(expected[entry.pluginId]))) {
      hydrated[entry.pluginId] = entry.read(snapshot[entry.pluginId]);
    }
  }
  return JSON.stringify(hydrated) === JSON.stringify(drafts) ? drafts : hydrated;
}
