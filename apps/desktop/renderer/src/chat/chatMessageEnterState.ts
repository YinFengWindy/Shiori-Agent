/**
 * Decides which chat rows play the enter animation. Only a message appended
 * to the end of the conversation after the current session was first shown
 * animates, and only once:
 * - a session switch (or first mount) marks everything present as seen;
 * - history pagination prepends rows before the first known one — seen, never animated;
 * - virtualization unmounting and remounting a row does not replay it, because
 *   the animation window closes `chatMessageEnterWindowMs` after the append.
 */

/** Slightly longer than the 240ms animation so a row mounted a frame late still plays it whole. */
export const chatMessageEnterWindowMs = 320;

export type ChatMessageEnterState = {
  sessionKey: string;
  /** Every key ever shown in this session. */
  seen: ReadonlySet<string>;
  /** Keys appended after mount, with the time their animation window closes. */
  entering: ReadonlyMap<string, number>;
};

export const initialChatMessageEnterState: ChatMessageEnterState = {
  sessionKey: "",
  seen: new Set(),
  entering: new Map(),
};

/** Advances the tracker for the session's current message keys (oldest first). */
export function advanceChatMessageEnterState(
  state: ChatMessageEnterState,
  sessionKey: string,
  keys: readonly string[],
  now: number,
): ChatMessageEnterState {
  if (sessionKey !== state.sessionKey) {
    return { sessionKey, seen: new Set(keys), entering: new Map() };
  }
  let lastSeenIndex = -1;
  keys.forEach((key, index) => {
    if (state.seen.has(key)) lastSeenIndex = index;
  });
  let seen: Set<string> | null = null;
  let entering: Map<string, number> | null = null;
  keys.forEach((key, index) => {
    if (state.seen.has(key)) return;
    seen ??= new Set(state.seen);
    seen.add(key);
    // Before the newest known row means history was prepended above it.
    if (index < lastSeenIndex) return;
    entering ??= new Map(state.entering);
    entering.set(key, now + chatMessageEnterWindowMs);
  });
  if (!seen) return state;
  return { sessionKey, seen, entering: entering ?? state.entering };
}

/** Whether the row with this key should carry the enter animation right now. */
export function isChatMessageEntering(state: ChatMessageEnterState, key: string, now: number): boolean {
  const until = state.entering.get(key);
  return until !== undefined && now < until;
}

/** Drops animation windows that have closed; returns the same state when none did. */
export function pruneChatMessageEnterState(state: ChatMessageEnterState, now: number): ChatMessageEnterState {
  let entering: Map<string, number> | null = null;
  for (const [key, until] of state.entering) {
    if (now < until) continue;
    entering ??= new Map(state.entering);
    entering.delete(key);
  }
  return entering ? { ...state, entering } : state;
}
