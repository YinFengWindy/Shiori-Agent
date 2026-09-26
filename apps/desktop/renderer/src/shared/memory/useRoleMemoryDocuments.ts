import { useEffect, useState } from "react";
import type { RoleMemoryDocument, RoleMemoryDocumentsPayload } from "../types";

type LoadedDocuments = {
  roleId: string;
  documents: RoleMemoryDocument[];
  error: string;
  loading: boolean;
};

/** Keeps role-scoped document reads current across refreshes and role switches. */
export function useRoleMemoryDocuments(
  roleId: string,
  bridgeReady: boolean,
  read: (roleId: string) => Promise<RoleMemoryDocumentsPayload>,
) {
  const [revision, setRevision] = useState(0);
  const [loaded, setLoaded] = useState<LoadedDocuments | null>(null);

  useEffect(() => {
    if (!roleId || !bridgeReady) return;
    let cancelled = false;
    setLoaded({ roleId, documents: [], error: "", loading: true });
    void read(roleId).then((response) => {
      if (cancelled) return;
      if (response.role_id !== roleId) {
        setLoaded({ roleId, documents: [], error: "角色不匹配", loading: false });
        return;
      }
      setLoaded({ roleId, documents: response.documents, error: "", loading: false });
    }).catch((error: unknown) => {
      if (!cancelled) {
        setLoaded({ roleId, documents: [], error: error instanceof Error ? error.message : String(error), loading: false });
      }
    });
    return () => { cancelled = true; };
  }, [roleId, bridgeReady, read, revision]);

  const current = loaded?.roleId === roleId ? loaded : null;
  return {
    documents: current?.documents ?? [],
    loading: Boolean(roleId && bridgeReady && (!current || current.loading)),
    error: current?.error ?? "",
    refresh: () => setRevision((value) => value + 1),
  };
}
