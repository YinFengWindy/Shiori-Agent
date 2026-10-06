import { useEffect, useRef, useState } from "react";
import { errorMessage } from "../errors";
import { useLatestRef } from "../useLatestRef";
import type { PluginRpcClient } from "../rpc";

/**
 * Loads and explicitly saves one JSON-serializable plugin-owned document.
 * A null identity disables persistence. Changing client or identity discards late
 * results; failed reads never create defaults and failed saves retain dirty edits.
 * This hook reports local errors/dirty state and does not join host transactions.
 */
export function usePrivateDraft<T extends object>(client: PluginRpcClient, identity: string | null, operations: {
  load(): Promise<T>;
  save(value: T): Promise<T>;
  onDirtyChange?(dirty: boolean): void;
}) {
  const latest = useLatestRef(operations);
  const revision = useRef(0);
  const [draft, setDraft] = useState<T | null>(null);
  const [saved, setSaved] = useState<T | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [loadedScope, setLoadedScope] = useState<{ client: PluginRpcClient; identity: string } | null>(null);
  useEffect(() => {
    const current = ++revision.current;
    setDraft(null); setSaved(null); setLoadedScope(null); setError(""); setSaving(false);
    setLoading(identity !== null);
    if (identity !== null) {
      void latest.current.load().then((value) => {
        if (current === revision.current) { setDraft(value); setSaved(value); setLoadedScope({ client, identity }); }
      }).catch((cause) => { if (current === revision.current) setError(errorMessage(cause)); })
        .finally(() => { if (current === revision.current) setLoading(false); });
    }
    return () => { revision.current += 1; };
  }, [client, identity, latest]);
  const currentScope = loadedScope?.client === client && loadedScope.identity === identity;
  const visibleDraft = currentScope ? draft : null;
  const dirty = visibleDraft !== null && JSON.stringify(visibleDraft) !== JSON.stringify(saved);
  useEffect(() => { latest.current.onDirtyChange?.(dirty); }, [dirty, latest]);
  async function save() {
    if (!visibleDraft || saving) return;
    const current = revision.current;
    setSaving(true); setError("");
    try {
      const value = await latest.current.save(visibleDraft);
      if (current === revision.current) { setDraft(value); setSaved(value); }
    } catch (cause) { if (current === revision.current) setError(errorMessage(cause)); }
    finally { if (current === revision.current) setSaving(false); }
  }
  return { draft: visibleDraft, saved: currentScope ? saved : null, dirty, loading, saving, error, setDraft, save };
}
