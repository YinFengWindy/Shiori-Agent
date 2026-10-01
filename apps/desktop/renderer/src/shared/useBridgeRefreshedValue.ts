import { useCallback, useEffect, useRef, useState } from "react";
import { type BridgeEvent, errorMessage, useLatestRef } from "@shiori/sdk";

type BridgeRefreshedValueOptions<T> = {
  /** Loads and refreshes only while enabled (default true); the last value is kept when disabled. */
  enabled?: boolean;
  /** Fetches the value; a new identity (e.g. changed inputs) triggers a reload. */
  load: () => Promise<T>;
  /**
   * Bridge events after which the value may have changed: a set of event
   * methods, or a predicate for rules a method name cannot express. Must be
   * a stable reference.
   */
  refreshEvents: ReadonlySet<string> | ((event: BridgeEvent) => boolean);
  /** Maps a bridge event to an error that invalidates the value (e.g. the bridge exited); null ignores it. */
  failOn?: (event: BridgeEvent) => string | null;
  /** Called once per failed load that is still the latest request. */
  onError?: (error: unknown) => void;
  /** Called with every value the latest request publishes. */
  onLoaded?: (value: T) => void;
  /** Also reloads when the window regains focus (default true). */
  refreshOnFocus?: boolean;
  /**
   * A failed load keeps the last value, and a reload keeps the last error
   * until it settles (default false: a failure clears the value, and every
   * reload clears the error when it starts).
   */
  keepValueOnError?: boolean;
};

/**
 * A value loaded over the desktop bridge and kept fresh: it reloads when
 * enabled or when `load` changes, after the given bridge events and (unless
 * turned off) when the window regains focus; it never polls. Responses can
 * resolve out of order, so only the latest request may publish; a failed
 * load records the error and, unless `keepValueOnError`, clears the value.
 */
export function useBridgeRefreshedValue<T>({
  enabled = true, load, refreshEvents, failOn, onError, onLoaded, refreshOnFocus = true, keepValueOnError = false,
}: BridgeRefreshedValueOptions<T>) {
  const [value, setValue] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const requestRef = useRef(0);
  // Callbacks only read inside event handlers, so a new identity must not resubscribe.
  const failOnRef = useLatestRef(failOn);
  const onErrorRef = useLatestRef(onError);
  const onLoadedRef = useLatestRef(onLoaded);

  const refresh = useCallback(async () => {
    const request = ++requestRef.current;
    setLoading(true);
    if (!keepValueOnError) setError("");
    try {
      const loaded = await load();
      if (request !== requestRef.current) return;
      setValue(loaded);
      setError("");
      onLoadedRef.current?.(loaded);
      return loaded;
    } catch (loadError) {
      if (request !== requestRef.current) return;
      if (!keepValueOnError) setValue(null);
      setError(errorMessage(loadError, { includeDetail: true }));
      onErrorRef.current?.(loadError);
    } finally {
      if (request === requestRef.current) setLoading(false);
    }
  }, [load, keepValueOnError, onErrorRef, onLoadedRef]);

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
      const refreshes = typeof refreshEvents === "function" ? refreshEvents(event) : refreshEvents.has(event.method);
      if (refreshes) void refresh();
      const failure = failOnRef.current?.(event);
      if (failure !== null && failure !== undefined) fail(failure);
    });
    const handleFocus = () => { void refresh(); };
    if (refreshOnFocus) window.addEventListener("focus", handleFocus);
    return () => {
      // A disabled or replaced subscription must not publish late responses.
      requestRef.current += 1;
      offEvents();
      if (refreshOnFocus) window.removeEventListener("focus", handleFocus);
    };
  }, [enabled, refresh, refreshEvents, refreshOnFocus, fail, failOnRef]);

  return { value, error, loading, refresh, fail, markPending };
}
