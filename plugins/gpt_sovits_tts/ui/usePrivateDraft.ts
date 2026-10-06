import { useEffect, useRef, useState } from "react";
import { errorMessage, useLatestRef, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";

/** One private document lifecycle, shared by connection settings and the role editor. */
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
  const [loadedIdentity, setLoadedIdentity] = useState<string | null>(null);
  useEffect(() => {
    const current = ++revision.current;
    setDraft(null); setSaved(null); setLoadedIdentity(null); setError(""); setSaving(false);
    setLoading(identity !== null);
    if (identity !== null) {
      void latest.current.load().then((value) => {
        if (current === revision.current) { setDraft(value); setSaved(value); setLoadedIdentity(identity); }
      }).catch((cause) => { if (current === revision.current) setError(errorMessage(cause)); })
        .finally(() => { if (current === revision.current) setLoading(false); });
    }
    return () => { revision.current += 1; };
  }, [client, identity, latest]);
  const visibleDraft = loadedIdentity === identity ? draft : null;
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
  return { draft: visibleDraft, saved, dirty, loading, saving, error, setDraft, save };
}
