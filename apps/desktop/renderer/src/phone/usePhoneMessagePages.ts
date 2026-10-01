import { errorFeedbackText } from "@shiori/plugin-sdk/host-internal";
import { useCallback, useEffect, useRef, useState } from "react";
import { useLatestRef } from "@shiori/plugin-sdk";
import type { PhoneMessage, PhoneMessagePage } from "./phoneClient";
import { mergePhoneMessages } from "./phoneChatPresentation";

type PhoneMessagePagesState = {
  /** Loaded messages, oldest first; null until the newest page arrives. */
  messages: readonly PhoneMessage[] | null;
  /** Live messages that arrived before the newest page; joined after it. */
  early: readonly PhoneMessage[];
  hasMore: boolean;
  nextBeforeSeq: number | null;
  error: string;
};

const initialState: PhoneMessagePagesState = { messages: null, early: [], hasMore: false, nextBeforeSeq: null, error: "" };

/**
 * One paged stream of messages for the phone's chat page: the newest page
 * (`loadPage(null)`) when it mounts or `streamKey` changes, older pages on
 * `loadOlder`, and messages handed to `pushLive` appended (each once, by
 * id). `retry` reloads after an error. A new stream (or a retry) drops
 * whatever an older page still in flight would have brought.
 */
export function usePhoneMessagePages(streamKey: string, loadPage: (beforeSeq: number | null) => Promise<PhoneMessagePage>) {
  const [state, setState] = useState(initialState);
  const [attempt, setAttempt] = useState(0);
  const loadPageRef = useLatestRef(loadPage);
  // Scroll events fire faster than renders: this, not state, keeps one older page in flight.
  const loadingOlderRef = useRef(false);
  // Bumped per (re)load of the stream: a page answering an earlier one is stale.
  const generationRef = useRef(0);

  useEffect(() => {
    let current = true;
    generationRef.current += 1;
    loadingOlderRef.current = false;
    setState(initialState);
    loadPageRef.current(null).then(
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
        if (current) setState((previous) => ({ ...previous, error: errorFeedbackText(loadError) }));
      },
    );
    return () => { current = false; };
  }, [streamKey, attempt, loadPageRef]);

  const pushLive = useCallback((live: readonly PhoneMessage[]) => {
    setState((previous) => {
      if (!previous.messages) return { ...previous, early: mergePhoneMessages(previous.early, live) };
      const messages = mergePhoneMessages(previous.messages, live);
      return messages === previous.messages ? previous : { ...previous, messages };
    });
  }, []);

  const { hasMore, nextBeforeSeq } = state;
  const loadOlder = useCallback(async () => {
    if (!hasMore || nextBeforeSeq === null || loadingOlderRef.current) return;
    loadingOlderRef.current = true;
    const generation = generationRef.current;
    const stale = () => generation !== generationRef.current;
    try {
      const page = await loadPageRef.current(nextBeforeSeq);
      if (stale()) return;
      setState((previous) => ({
        ...previous,
        messages: mergePhoneMessages(page.messages, previous.messages ?? []),
        hasMore: page.hasMore,
        nextBeforeSeq: page.nextBeforeSeq,
      }));
    } catch (loadError) {
      if (!stale()) setState((previous) => ({ ...previous, error: errorFeedbackText(loadError) }));
    } finally {
      // A new stream already cleared the flag and may have its own page in flight.
      if (!stale()) loadingOlderRef.current = false;
    }
  }, [hasMore, nextBeforeSeq, loadPageRef]);

  const retry = useCallback(() => setAttempt((value) => value + 1), []);
  return { messages: state.messages, hasMore, error: state.error, loadOlder, retry, pushLive };
}
