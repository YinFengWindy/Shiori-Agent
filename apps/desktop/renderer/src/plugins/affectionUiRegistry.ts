import { useSyncExternalStore, type ComponentType } from "react";
import type { PluginChatAffectionProps, PluginRoleAffectionProps } from "@yinfengwindy/shiori-sdk";
import { PluginContributionRegistry } from "./pluginContributionRegistry";

/** One plugin's 「好感度」 tab, already bound to that plugin's client. */
export type RoleAffectionEntry = {
  pluginId: string;
  Component: ComponentType<PluginRoleAffectionProps>;
};

/** One plugin's chat affection block, already bound to that plugin's client. */
export type ChatAffectionEntry = {
  pluginId: string;
  Component: ComponentType<PluginChatAffectionProps>;
};

const roleEntries = new PluginContributionRegistry<RoleAffectionEntry>("affectionUiRegistry", "roleAffection");
const chatEntries = new PluginContributionRegistry<ChatAffectionEntry>("affectionUiRegistry", "chatAffection");
// The first entry of each slot. Unchanged entries keep their reference, so
// useSyncExternalStore sees the same snapshot until a slot really changes.
let roleSnapshot: RoleAffectionEntry | null = null;
let chatSnapshot: ChatAffectionEntry | null = null;
const listeners = new Set<() => void>();

function publish() {
  roleSnapshot = roleEntries.list()[0] ?? null;
  chatSnapshot = chatEntries.list()[0] ?? null;
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Registers affection slots. The first plugin to claim a slot wins. */
export const affectionUiRegistry = {
  registerRole(entry: RoleAffectionEntry) {
    roleEntries.register(entry);
    publish();
  },
  registerChat(entry: ChatAffectionEntry) {
    chatEntries.register(entry);
    publish();
  },
  /** Drops the plugin from both slots. */
  unregister(pluginId: string) {
    roleEntries.unregister(pluginId);
    chatEntries.unregister(pluginId);
    publish();
  },
};

/** The registered role tab, or null. Stable until the registry changes. */
export function useRoleAffectionContribution() {
  return useSyncExternalStore(subscribe, () => roleSnapshot, () => roleSnapshot);
}

/** The registered chat meter, or null. Stable until the registry changes. */
export function useChatAffectionContribution() {
  return useSyncExternalStore(subscribe, () => chatSnapshot, () => chatSnapshot);
}
