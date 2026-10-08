import { useLayoutEffect, useRef, useState } from "react";
import type { PluginRpcClient } from "../rpc";
import { useLatestRef } from "../useLatestRef";
import {
  PrivateAutosaveSession,
  emptyPrivateAutosaveState,
  privateAutosaveDebounceMs,
  type PrivateAutosaveOperations,
  type PrivateAutosaveState,
} from "./privateAutosaveSession";

/** Options of `usePrivateAutosave`: the document's operations and an optional quiet period. */
export type PrivateAutosaveOptions<T> = PrivateAutosaveOperations<T> & {
  /** Quiet period merging consecutive `update`s into one save; read when a scope starts. Default 400 ms. */
  debounceMs?: number;
};

type ScopedState<T extends object> = PrivateAutosaveState<T> & { session: PrivateAutosaveSession<T> | null };

/**
 * Loads one JSON-serializable plugin-owned document and autosaves it like the
 * host's own settings pages (#652, #683). A null identity disables loading and saving.
 *
 * - `update(change)` edits the draft and saves the latest draft once edits pause
 *   (`debounceMs`); saves never overlap, and an edit made during a save is saved after it.
 * - `commit(change?)` saves at once, for a field that takes effect on blur/Enter.
 *   Keep such a field's unvalidated text in component state and pass the
 *   validated value to `commit`; the draft is one document, so anything written
 *   to it is saved with the next save.
 * - Unmounting or changing `client`/`identity` submits the last scheduled draft
 *   to the scope it was edited in; late results of an earlier scope are discarded.
 * - A failed save keeps the draft and pauses autosave (`savePhase` "error",
 *   `saveError`); edits made meanwhile are kept. `retry()` resubmits the failed
 *   draft, then the newest edit.
 * - A failed read leaves `draft` null with `loadError` and never saves a default.
 *   `reload()` is meant for that state: it reads again. Once the document has
 *   loaded it also drops unsaved edits and the scheduled save, and it does
 *   nothing while a save is in flight, since that read could return the
 *   document from before the save.
 *
 * `savePhase` drives `host.ui.SettingsSavedStatus`.
 */
export function usePrivateAutosave<T extends object>(client: PluginRpcClient, identity: string | null, options: PrivateAutosaveOptions<T>) {
  const [state, setState] = useState<ScopedState<T>>({ ...emptyPrivateAutosaveState, session: null });
  const [reloads, setReloads] = useState(0);
  const sessionRef = useRef<PrivateAutosaveSession<T> | null>(null);
  // The session the last cleanup retired, until the next run decides its pending work.
  const retiringRef = useRef<PrivateAutosaveSession<T> | null>(null);
  const latest = useLatestRef(options);

  // A layout effect: its cleanup runs before `latest` adopts the next scope's
  // operations, so a retired session keeps writing through its own.
  useLayoutEffect(() => {
    const retiring = retiringRef.current;
    retiringRef.current = null;
    if (retiring) {
      // Only `reload` re-runs this effect for the same scope, and it drops pending
      // work; a scope change (even together with a reload) submits it.
      if (retiring.client === client && retiring.identity === identity) retiring.discard();
      else retiring.end();
    }
    if (identity === null) {
      setState({ ...emptyPrivateAutosaveState, session: null });
      return undefined;
    }
    const session: PrivateAutosaveSession<T> = new PrivateAutosaveSession<T>(client, identity, latest, (patch) => {
      setState((current) => current.session === session ? { ...current, ...patch } : current);
    }, latest.current.debounceMs ?? privateAutosaveDebounceMs);
    sessionRef.current = session;
    setState({ ...emptyPrivateAutosaveState, session });
    session.load();
    return () => {
      if (sessionRef.current === session) sessionRef.current = null;
      session.retire();
      retiringRef.current = session;
    };
  }, [client, identity, reloads, latest]);
  // Declared after the session effect, so on unmount it runs after that cleanup.
  useLayoutEffect(() => () => {
    retiringRef.current?.end();
    retiringRef.current = null;
  }, []);

  const [actions] = useState(() => ({
    /** Edits the draft and saves it once edits pause. */
    update: (change: (current: T) => T) => sessionRef.current?.update(change),
    /** Optionally edits, then saves the draft at once. */
    commit: (change?: (current: T) => T) => sessionRef.current?.commit(change),
    /** Resubmits a failed save, then the newest edit. */
    retry: () => sessionRef.current?.retry(),
    /** Reads the document again after a failed read; see the hook's notes. */
    reload: () => {
      const session = sessionRef.current;
      if (!session || session.isSaving) return;
      setReloads((count) => count + 1);
    },
  }));

  // Hide another scope's state during the render before its own session starts.
  const { session, ...view } = state;
  const current = session?.client === client && session.identity === identity;
  return { ...(current ? view : { ...emptyPrivateAutosaveState, loading: identity !== null }), ...actions };
}
