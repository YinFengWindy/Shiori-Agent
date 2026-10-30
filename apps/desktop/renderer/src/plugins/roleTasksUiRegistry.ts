import { useSyncExternalStore, type ComponentType } from "react";
import type { PluginRoleTasksProps } from "@yinfengwindy/shiori-sdk";
import { PluginContributionRegistry } from "./pluginContributionRegistry";

/** One plugin's block in the chat task panel, already bound to that plugin's client. */
export type RoleTasksEntry = {
  pluginId: string;
  Component: ComponentType<PluginRoleTasksProps>;
};

const entries = new PluginContributionRegistry<RoleTasksEntry>("roleTasksUiRegistry", "roleTasks");
// The first entry. An unchanged entry keeps its reference, so
// useSyncExternalStore sees the same snapshot until the slot really changes.
let snapshot: RoleTasksEntry | null = null;
const listeners = new Set<() => void>();

function publish() {
  snapshot = entries.list()[0] ?? null;
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Registers the task panel's plugin block. The first plugin to claim it wins. */
export const roleTasksUiRegistry = {
  register(entry: RoleTasksEntry) {
    entries.register(entry);
    publish();
  },
  unregister(pluginId: string) {
    entries.unregister(pluginId);
    publish();
  },
};

/** The registered block, or null. Stable until the registry changes. */
export function useRoleTasksContribution() {
  return useSyncExternalStore(subscribe, () => snapshot, () => snapshot);
}
