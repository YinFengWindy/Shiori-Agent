import { useCallback, useEffect, useRef, useState } from "react";
import type { BridgeEvent } from "../../../src/bridge/shared";
import { errorMessage } from "./feedback/feedbackStore";
import { useLatestRef } from "./useLatestRef";

type BridgeRefreshedValueOptions<T> = {
  /** Loads and refreshes only while enabled; the last value is kept when disabled. */
  enabled: boolean;
  /** Fetches the value; a new identity (e.g. changed inputs) triggers a reload. */
  load: () => Promise<T>;
  /** Bridge event methods after which the value may have changed. */
  refreshEvents: ReadonlySet<string>;
  /** Maps a bridge event to an error that invalidates the value (e.g. the bridge exited); null ignores it. */
  failOn?: (event: BridgeEvent) => string | null;
  /** Called once per failed load that is still the latest request. */
  onError?: (error: unknown) => void;
};

/**
 * A value loaded over the desktop bridge and kept fresh: it reloads when
 * enabled or when `load` changes, after the given bridge events and when the
 * window regains focus; it never polls. Responses can resolve out of order, so
 * only the latest request may publish; a failed load clears the value and
 * records the error.
 */
export function useBridgeRefreshedValue<T>({ enabled, load, refreshEvents, failOn, onError }: BridgeRefreshedValueOptions<T>) {
  const [value, setValue] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const requestRef = useRef(0);
  // Callbacks only read inside event handlers, so a new identity must not resubscribe.
  const failOnRef = useLatestRef(failOn);
  const onErrorRef = useLatestRef(onError);

  const refresh = useCallback(async () => {
    const request = ++requestRef.current;
    setLoading(true);
    setError("");
    try {
      const loaded = await load();
      if (request !== requestRef.current) return;
      setValue(loaded);
      return loaded;
    } catch (loadError) {
      if (request !== requestRef.current) return;
      setValue(null);
      setError(errorMessage(loadError));
      onErrorRef.current?.(loadError);
    } finally {
      if (request === requestRef.current) setLoading(false);
    }
  }, [load, onErrorRef]);

  /** Drops any in-flight load and shows `message` instead of a value. */
  const fail = useCallback((message: string) => {
    requestRef.current += 1;
    setValue(null);
    setLoading(false);
    setError(message);
  }, []);

  /** Marks a load that the caller starts by other means (e.g. restarting the bridge first). */
  const markPending = useCallback(() => {
    setLoading(true);
    setError("");
  }, []);

  useEffect(() => {
    if (!enabled) return;
    void refresh();
    const offEvents = window.miraDesktop.onEvent((event) => {
      if (refreshEvents.has(event.method)) void refresh();
      const failure = failOnRef.current?.(event);
      if (failure !== null && failure !== undefined) fail(failure);
    });
    const handleFocus = () => { void refresh(); };
    window.addEventListener("focus", handleFocus);
    return () => {
      // A disabled or replaced subscription must not publish late responses.
      requestRef.current += 1;
      offEvents();
      window.removeEventListener("focus", handleFocus);
    };
  }, [enabled, refresh, refreshEvents, fail, failOnRef]);

  return { value, error, loading, refresh, fail, markPending };
}
