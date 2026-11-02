import { createPluginRpcClient } from "./pluginBridgeClient";
import type { PluginRoleValues } from "@yinfengwindy/shiori-sdk";
import { pluginRoleSettingsRegistry } from "./pluginFeatureRegistry";
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
    .filter((entry) => entry.storage === "plugin" && !entry.save && isPluginEnabled(entry.pluginId)
      && drafts[entry.pluginId] !== undefined
      && JSON.stringify(drafts[entry.pluginId]) !== JSON.stringify(entry.read(pluginState[entry.pluginId] ?? {})))
    .map((entry) => [entry.pluginId, drafts[entry.pluginId]]));
}

/** Notifies core-committed contributions, or one RPC contribution after its own commit. */
export async function notifyPluginRoleSaved(drafts: PluginRoleSettingsDraft, previousRuntime: Record<string, unknown> = {}, previousState: PluginRoleSettingsDraft = {}, savedPluginId?: string) {
  const previous = readPluginRoleSettings(previousRuntime, previousState);
  await Promise.all(pluginRoleSettingsRegistry.list().filter((entry) => isPluginEnabled(entry.pluginId)
    && (savedPluginId !== undefined ? entry.pluginId === savedPluginId : entry.storage !== "plugin" || !entry.save)
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

/** Reconciles independent projections, retaining fields edited since the supplied draft. */
export function refreshPluginRoleDrafts(drafts: PluginRoleSettingsDraft, snapshot: PluginRoleSettingsDraft = {}, expected?: PluginRoleSettingsDraft) {
  const hydrated = { ...drafts };
  for (const entry of pluginRoleSettingsRegistry.list()) {
    if (entry.storage !== "plugin" || snapshot[entry.pluginId] === undefined) continue;
    const values = { ...entry.read(snapshot[entry.pluginId]) };
    const current = drafts[entry.pluginId];
    if (expected !== undefined && current !== undefined) {
      const previous = expected[entry.pluginId] ?? {};
      for (const field of new Set([...Object.keys(current), ...Object.keys(previous)])) {
        if (Object.hasOwn(current, field) === Object.hasOwn(previous, field)
          && JSON.stringify(current[field]) === JSON.stringify(previous[field])) continue;
        if (Object.hasOwn(current, field)) values[field] = current[field];
        else delete values[field];
      }
    }
    hydrated[entry.pluginId] = values;
  }
  return JSON.stringify(hydrated) === JSON.stringify(drafts) ? drafts : hydrated;
}

/** Persists RPC drafts; communication cleanup errors are reported separately from writes. */
export async function savePluginRoleSettings(roleId: string, drafts: PluginRoleSettingsDraft, previousState: PluginRoleSettingsDraft, onSaved: (pluginId: string, snapshot: PluginRoleValues) => Promise<void>, onPostSaveError: (error: unknown) => void) {
  for (const entry of pluginRoleSettingsRegistry.list()) {
    if (entry.storage !== "plugin" || !entry.save || !isPluginEnabled(entry.pluginId)) continue;
    const values = drafts[entry.pluginId];
    const previous = entry.read(previousState[entry.pluginId] ?? {});
    if (!values || JSON.stringify(values) === JSON.stringify(previous)) continue;
    const client = createPluginRpcClient(entry.pluginId);
    try { await onSaved(entry.pluginId, await entry.save(roleId, values, previous, client)); }
    finally {
      try { await client.dispose(); }
      catch (error: unknown) { onPostSaveError(error); }
    }
  }
}
