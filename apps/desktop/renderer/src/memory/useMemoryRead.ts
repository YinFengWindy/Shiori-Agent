import { errorFeedbackText } from "@yinfengwindy/shiori-sdk/host-internal";
import { useEffect, useState } from "react";
import { useLatestRef } from "@yinfengwindy/shiori-sdk";

/**
 * One memory read. `scope` is the reset boundary (role, filters, refresh):
 * a new scope drops the previous value. `key` identifies this read inside its
 * scope; a new key in the same scope (the next batch, or a retry) keeps
 * showing the settled value until it arrives and, with `merge`, combines the two.
 */
export type MemoryReadRequest<T> = {
  scope: string;
  key: string;
  read: () => Promise<T>;
  merge?: (previous: T, next: T) => T;
};

/** What a memory view renders from one read. */
export type MemoryReadState<T> = {
  /** Settled value of the current scope; null before its first response. */
  value: T | null;
  loading: boolean;
  /** Failure of the current key; earlier batches of the scope stay in `value`. */
  error: string;
};

type Settled<T> = { scope: string; key: string; value: T | null; error: string };

/**
 * The memory module's single "read -> drop stale responses -> loading / error"
 * primitive, shared by documents, the timeline list and item details. A
 * response only lands while its key is still current, so role switches,
 * filter changes and refreshes never show an older answer. Pass `null` when
 * there is nothing to read.
 */
export function useMemoryRead<T>(request: MemoryReadRequest<T> | null): MemoryReadState<T> {
  const [settled, setSettled] = useState<Settled<T> | null>(null);
  const latest = useLatestRef(request);
  const scope = request?.scope;
  const key = request?.key;

  useEffect(() => {
    const current = latest.current;
    if (!current) return;
    let cancelled = false;
    current.read().then((next) => {
      if (cancelled) return;
      setSettled((previous) => {
        // Only a settled value of this very scope is a batch to append to.
        const base = previous?.scope === current.scope ? previous.value : null;
        const value = base !== null && current.merge ? current.merge(base, next) : next;
        return { scope: current.scope, key: current.key, value, error: "" };
      });
    }, (error: unknown) => {
      if (cancelled) return;
      setSettled((previous) => ({
        scope: current.scope,
        key: current.key,
        value: previous?.scope === current.scope ? previous.value : null,
        error: errorFeedbackText(error),
      }));
    });
    return () => { cancelled = true; };
  }, [scope, key, latest]);

  const inScope = request && settled?.scope === request.scope ? settled : null;
  return {
    value: inScope?.value ?? null,
    loading: request !== null && settled?.key !== request.key,
    error: request && settled?.key === request.key ? settled.error : "",
  };
}
