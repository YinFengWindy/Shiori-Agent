const synchronousDesktopBridgeEvents = new Set([
  "bridge.exit",
  "chat.delta",
  "chat.done",
  "chat.error",
  "session.updated",
]);

/** Returns whether a bridge event must update renderer state in arrival order. */
export function shouldProcessDesktopBridgeEventSynchronously(method: string): boolean {
  return synchronousDesktopBridgeEvents.has(method);
}
