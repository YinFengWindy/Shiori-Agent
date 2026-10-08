import { useState } from "react";
import { MemoryDocumentView } from "./MemoryDocumentView";
import type { MemoryTab, RoleMemoryDocumentsPayload } from "./memoryDocuments";
import { MemoryNav } from "./MemoryNav";
import { memoryReadKey, readMemoryDocuments, type MemoryReadContext, type MemoryRpc } from "./memoryReads";
import { MemoryTimeline } from "./MemoryTimeline";
import { useScopedRead } from "../shared/useScopedRead";

/**
 * The whole role memory page, rendered by the host from the configured
 * memory plugin's standard `roles.memory.*` reads. Documents load once per
 * refresh so switching tabs is instant; refresh re-reads documents and the
 * semantic layer together.
 */
export function RoleMemoryPage({ client, roleId }: { client: MemoryRpc; roleId: string }) {
  const [tab, setTab] = useState<MemoryTab>("timeline");
  const [refreshKey, setRefreshKey] = useState(0);
  const context: MemoryReadContext = { client, roleId, refreshKey };
  const documentsKey = memoryReadKey(context, "documents");
  const documents = useScopedRead<RoleMemoryDocumentsPayload>({
    scope: documentsKey,
    key: documentsKey,
    read: () => readMemoryDocuments(context),
  });
  return <section className="grid gap-4" aria-label="角色记忆" data-testid="role-memory-panel">
    <MemoryNav tab={tab} onTab={setTab} onRefresh={() => setRefreshKey((value) => value + 1)} />
    <div role="tabpanel">
      {tab === "timeline"
        ? <MemoryTimeline context={context} />
        : <MemoryDocumentView name={tab} documents={documents} />}
    </div>
  </section>;
}
