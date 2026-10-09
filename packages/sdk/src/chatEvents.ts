/**
 * Host bridge events that end a chat turn (runtime API 3.1.1): while the
 * bridge connection is open, every started turn ends with exactly one of them.
 * `chat.cancelled` (`{session_key, turn_id}`) marks a turn cancelled by turn id
 * or by bridge shutdown.
 */
export const chatTerminalEventMethods = ["chat.done", "chat.error", "chat.cancelled"] as const;

/** One of {@link chatTerminalEventMethods}. */
export type ChatTerminalEventMethod = (typeof chatTerminalEventMethods)[number];

/** Whether a bridge event method ends a chat turn. */
export function isChatTerminalEvent(method: string): method is ChatTerminalEventMethod {
  return (chatTerminalEventMethods as readonly string[]).includes(method);
}
