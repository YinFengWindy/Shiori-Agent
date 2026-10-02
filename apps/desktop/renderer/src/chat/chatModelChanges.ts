type Listener = (roleId: string, pending: boolean) => void;
const listeners = new Set<Listener>();

/** Invalidate context responses as soon as model selection begins changing. */
export function notifyChatModelChange(roleId: string, pending: boolean) {
  for (const listener of listeners) listener(roleId, pending);
}

/** Subscribe to selection changes owned by the existing model selection hook. */
export function subscribeChatModelChanges(listener: Listener) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
