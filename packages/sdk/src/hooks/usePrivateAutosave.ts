import { useEffect, useRef, useState } from "react";
import type { PluginRpcClient } from "../rpc";
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
 * - `stage(change)` edits without scheduling a save, for a field that only takes
 *   effect on blur/Enter; `commit(change?)` then saves the draft at once. A staged
 *   edit is never saved on its own when the editor leaves.
 * - Unmounting or changing `client`/`identity` submits the last scheduled draft
 *   to the scope it was edited in; late results of an earlier scope are discarded.
 * - A failed save keeps the draft, pauses autosave (`savePhase` "error",
 *   `saveError`) until `retry()`, which resubmits it and then any newer edit.
 * - A failed read leaves `draft` null with `loadError` and never saves a default;
 *   `reload()` reads again, dropping unsaved edits and any pending save.
 *
 * `savePhase` drives `host.ui.SettingsSavedStatus`. Use `usePrivateDraft` instead
 * where the user saves explicitly.
 */
export function usePrivateAutosave<T extends object>(client: PluginRpcClient, identity: string | null, options: PrivateAutosaveOptions<T>) {
  const [state, setState] = useState<ScopedState<T>>({ ...emptyPrivateAutosaveState, session: null });
  const [reloads, setReloads] = useState(0);
  const sessionRef = useRef<PrivateAutosaveSession<T> | null>(null);
  const optionsRef = useRef(options);

  useEffect(() => {
    optionsRef.current = options;
    const session = sessionRef.current;
    if (session?.client === client && session.identity === identity) session.setOperations(options);
  });

  useEffect(() => {
    if (identity === null) {
      setState({ ...emptyPrivateAutosaveState, session: null });
      return undefined;
    }
    const { debounceMs = privateAutosaveDebounceMs } = optionsRef.current;
    const session: PrivateAutosaveSession<T> = new PrivateAutosaveSession<T>(client, identity, optionsRef.current, (patch) => {
      setState((current) => current.session === session ? { ...current, ...patch } : current);
    }, debounceMs);
    sessionRef.current = session;
    setState({ ...emptyPrivateAutosaveState, session });
    session.load();
    return () => {
      if (sessionRef.current === session) sessionRef.current = null;
      // A reload abandons the old session's pending work; departure submits it.
      session.end(!session.reloading);
    };
  }, [client, identity, reloads]);

  const [actions] = useState(() => ({
    /** Edits the draft and saves it once edits pause. */
    update: (change: (current: T) => T) => sessionRef.current?.edit(change, "debounced"),
    /** Edits the draft without scheduling a save (blur/Enter fields). */
    stage: (change: (current: T) => T) => sessionRef.current?.edit(change, "none"),
    /** Optionally edits, then saves the draft at once. */
    commit: (change?: (current: T) => T) => sessionRef.current?.edit(change, "now"),
    /** Resubmits a failed save. */
    retry: () => sessionRef.current?.retry(),
    /** Reads the document again, discarding unsaved edits. */
    reload: () => {
      const session = sessionRef.current;
      if (!session) return;
      session.reloading = true;
      setReloads((count) => count + 1);
    },
  }));

  // Hide another scope's state during the render before its own session starts.
  const { session, ...view } = state;
  const current = session?.client === client && session.identity === identity;
  return { ...(current ? view : { ...emptyPrivateAutosaveState, loading: identity !== null }), ...actions };
}
