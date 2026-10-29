import { useSyncExternalStore, type ComponentType } from "react";
import type { PluginChatAffectionProps, PluginRoleAffectionProps } from "@yinfengwindy/shiori-sdk";

/** One plugin's 「好感度」 tab, already bound to that plugin's client. */
export type RoleAffectionEntry = {
  pluginId: string;
  Component: ComponentType<PluginRoleAffectionProps>;
};

/** One plugin's chat affection meter. */
export type ChatAffectionEntry = {
  pluginId: string;
  Component: ComponentType<PluginChatAffectionProps>;
};

const roleEntries = new Map<string, RoleAffectionEntry>();
const chatEntries = new Map<string, ChatAffectionEntry>();
let roleSnapshot: RoleAffectionEntry | null = null;
let chatSnapshot: ChatAffectionEntry | null = null;
const listeners = new Set<() => void>();

function publish() {
  roleSnapshot = roleEntries.values().next().value ?? null;
  chatSnapshot = chatEntries.values().next().value ?? null;
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Registers affection slots. The first plugin to claim a slot wins. */
export const affectionUiRegistry = {
  registerRole(entry: RoleAffectionEntry) {
    if (roleEntries.has(entry.pluginId)) return;
    roleEntries.set(entry.pluginId, entry);
    publish();
  },
  registerChat(entry: ChatAffectionEntry) {
    if (chatEntries.has(entry.pluginId)) return;
    chatEntries.set(entry.pluginId, entry);
    publish();
  },
  unregister(pluginId: string) {
    const changed = roleEntries.delete(pluginId) || chatEntries.delete(pluginId);
    if (changed) publish();
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
