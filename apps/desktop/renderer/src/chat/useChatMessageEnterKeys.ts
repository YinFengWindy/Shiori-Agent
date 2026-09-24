import { useEffect, useLayoutEffect, useMemo, useState } from "react";
import { getChatMessageReactKey } from "./chatMessageIdentity";
import {
  advanceChatMessageEnterState,
  chatMessageEnterWindowMs,
  initialChatMessageEnterState,
  pruneChatMessageEnterState,
} from "./chatMessageEnterState";
import type { SessionMessage } from "../shared/types";

/**
 * Returns the render keys of messages that should play the enter animation
 * right now (see `chatMessageEnterState`). Advanced in a layout effect so the
 * class lands before the new row's first paint.
 */
export function useChatMessageEnterKeys(sessionKey: string, messages: readonly SessionMessage[]): ReadonlySet<string> {
  const [state, setState] = useState(initialChatMessageEnterState);
  const keys = useMemo(() => messages.map((message, index) => getChatMessageReactKey(message, index)), [messages]);

  useLayoutEffect(() => {
    setState((current) => advanceChatMessageEnterState(current, sessionKey, keys, performance.now()));
  }, [keys, sessionKey]);

  useEffect(() => {
    if (!state.entering.size) return undefined;
    const timer = window.setTimeout(() => {
      setState((current) => pruneChatMessageEnterState(current, performance.now()));
    }, chatMessageEnterWindowMs + 16);
    return () => window.clearTimeout(timer);
  }, [state.entering]);

  return useMemo(() => new Set(state.entering.keys()), [state.entering]);
}
