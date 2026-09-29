import { useCallback, useEffect, useRef, useState } from "react";
import { errorMessage } from "@shiori/plugin-sdk";
import { createPhoneClient, type PhoneMessage } from "./phoneClient";
import { mergePhoneMessages } from "./phoneChatPresentation";
import { usePhoneLiveUpdates } from "./usePhoneLiveUpdates";

const client = createPhoneClient();

type PhoneChatState = {
  /** Loaded messages, oldest first; null until the newest page arrives. */
  messages: readonly PhoneMessage[] | null;
  /** Live messages that arrived before the newest page; joined after it. */
  early: readonly PhoneMessage[];
  hasMore: boolean;
  nextBeforeSeq: number | null;
  error: string;
};

const initialState: PhoneChatState = { messages: null, early: [], hasMore: false, nextBeforeSeq: null, error: "" };

/**
 * One conversation's messages for the phone's chat page: the newest page
 * when it mounts, older pages on `loadOlder`, and messages committed while
 * it is open appended live (each once, by id). `retry` reloads after an error.
 */
export function usePhoneChatMessages(roleId: string, threadId: string) {
  const [state, setState] = useState(initialState);
  const [attempt, setAttempt] = useState(0);
  // Scroll events fire faster than renders: this, not state, keeps one older page in flight.
  const loadingOlderRef = useRef(false);

  useEffect(() => {
    let current = true;
    setState(initialState);
    client.listMessages(roleId, threadId, null).then(
      (page) => {
        if (!current) return;
        setState((previous) => ({
          ...previous,
          messages: mergePhoneMessages(page.messages, previous.early),
          early: [],
          hasMore: page.hasMore,
          nextBeforeSeq: page.nextBeforeSeq,
        }));
      },
      (loadError: unknown) => {
        if (current) setState((previous) => ({ ...previous, error: errorMessage(loadError) }));
      },
    );
    return () => { current = false; };
  }, [roleId, threadId, attempt]);

  usePhoneLiveUpdates(roleId, (update) => {
    if (update.threadId !== threadId) return;
    setState((previous) => {
      if (!previous.messages) return { ...previous, early: mergePhoneMessages(previous.early, update.messages) };
      const messages = mergePhoneMessages(previous.messages, update.messages);
      return messages === previous.messages ? previous : { ...previous, messages };
    });
  });

  const { hasMore, nextBeforeSeq } = state;
  const loadOlder = useCallback(async () => {
    if (!hasMore || nextBeforeSeq === null || loadingOlderRef.current) return;
    loadingOlderRef.current = true;
    try {
      const page = await client.listMessages(roleId, threadId, nextBeforeSeq);
      setState((previous) => ({
        ...previous,
        messages: mergePhoneMessages(page.messages, previous.messages ?? []),
        hasMore: page.hasMore,
        nextBeforeSeq: page.nextBeforeSeq,
      }));
    } catch (loadError) {
      setState((previous) => ({ ...previous, error: errorMessage(loadError) }));
    } finally {
      loadingOlderRef.current = false;
    }
  }, [roleId, threadId, hasMore, nextBeforeSeq]);

  const retry = useCallback(() => setAttempt((value) => value + 1), []);
  return { messages: state.messages, hasMore, error: state.error, loadOlder, retry };
}
