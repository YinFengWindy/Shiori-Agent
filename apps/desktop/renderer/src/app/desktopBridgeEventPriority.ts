import { chatTerminalEventMethods } from "@yinfengwindy/shiori-sdk";

const synchronousDesktopBridgeEvents = new Set<string>([
  "bridge.exit",
  "chat.delta",
  "chat.tool.started",
  "chat.tool.completed",
  ...chatTerminalEventMethods,
  "session.updated",
]);

/** Returns whether a bridge event must update renderer state in arrival order. */
export function shouldProcessDesktopBridgeEventSynchronously(method: string): boolean {
  return synchronousDesktopBridgeEvents.has(method);
}
