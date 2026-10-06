import { useSyncExternalStore } from "react";

const entries = new Map<symbol, { roleId: string; dirty: boolean }>();
const listeners = new Set<() => void>();
const publish = () => { for (const listener of listeners) listener(); };
const subscribe = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };

/** A mount-scoped report cannot clear another editor or a later role's pending edits. */
export function createRoleUiDirtyLease(roleId: string) {
  const token = Symbol(roleId);
  let disposed = false;
  return {
    activate() { disposed = false; },
    set(dirty: boolean) {
      if (disposed) return;
      const entry = entries.get(token);
      if ((entry?.dirty ?? false) !== dirty) { entries.set(token, { roleId, dirty }); publish(); }
    },
    dispose() { disposed = true; if (entries.delete(token)) publish(); },
  };
}

/** Reads only a stable boolean for the current role's independent editor drafts. */
export function usePluginRoleUiDirty(roleId: string | null) {
  return useSyncExternalStore(subscribe, () => [...entries.values()].some((entry) => entry.roleId === roleId && entry.dirty), () => false);
}
