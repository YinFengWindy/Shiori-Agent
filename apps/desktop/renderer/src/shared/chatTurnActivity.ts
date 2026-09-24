// How many chat turns the renderer is currently waiting on (sent and not yet
// done / failed / cancelled). Published by the app shell from its
// `sendingSessions` state and read at click time by actions that would cut a
// turn off, such as the plugins page's app relaunch — which sits deep inside
// settings with no prop path to the shell. A plain module value is enough:
// readers only need the current count when the user acts, not re-renders.
let inFlightChatTurns = 0;

/** Records the number of chat turns currently in flight. */
export function setInFlightChatTurns(count: number): void {
  inFlightChatTurns = Math.max(0, count);
}

/** Whether any chat turn is still streaming or waiting for its first token. */
export function hasInFlightChatTurns(): boolean {
  return inFlightChatTurns > 0;
}
