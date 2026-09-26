import { useCallback, useState } from "react";
import type { PluginRoleMemoryComponentProps, PluginUiModule } from "../../../apps/desktop/renderer/src/plugins/pluginUiModuleContract";
import { MemoryDocumentPane, MemoryDocumentTabs, MemoryRefreshButton } from "../../../apps/desktop/renderer/src/shared/memory/RoleMemoryDocumentParts";
import { useRoleMemoryDocuments } from "../../../apps/desktop/renderer/src/shared/memory/useRoleMemoryDocuments";
import { RoleSemanticMemoryPane } from "../../../apps/desktop/renderer/src/shared/memory/RoleSemanticMemoryParts";
import { initialSemanticQuery, type RoleSemanticDetail, type RoleSemanticList, type RoleSemanticQuery } from "../../../apps/desktop/renderer/src/shared/memory/roleSemanticMemory";
import { useRoleSemanticMemory } from "../../../apps/desktop/renderer/src/shared/memory/useRoleSemanticMemory";
import type { RoleMemoryDocument, RoleMemoryDocumentsPayload } from "../../../apps/desktop/renderer/src/shared/types";

/** Default memory plugin's role-detail Dashboard. */
export function DefaultMemoryDashboard({ roleId, bridgeReady, client, host }: PluginRoleMemoryComponentProps) {
  const [selected, setSelected] = useState<RoleMemoryDocument["name"]>("SELF.md");
  const [query, setQuery] = useState<RoleSemanticQuery>(initialSemanticQuery);
  const [selectedId, setSelectedId] = useState("");
  const read = useCallback((id: string) => client.call<RoleMemoryDocumentsPayload>("roles.memory.documents", { role_id: id }), [client]);
  const readList = useCallback((id: string, options: RoleSemanticQuery) => client.call<RoleSemanticList>("roles.memory.semantic.list", { role_id: id, ...options }), [client]);
  const readDetail = useCallback((id: string, itemId: string) => client.call<RoleSemanticDetail>("roles.memory.semantic.detail", { role_id: id, item_id: itemId }), [client]);
  const documents = useRoleMemoryDocuments(roleId, bridgeReady, read);
  const semantic = useRoleSemanticMemory(roleId, bridgeReady, query, selectedId, readList, readDetail);
  const refresh = () => { documents.refresh(); semantic.refresh(); };
  return <section className="grid gap-5" aria-label="角色记忆" data-testid="role-memory-panel">
    <header className="flex items-center justify-between gap-3">
      <h2 className="m-0 text-title-sm text-ink">默认记忆</h2>
      <MemoryRefreshButton disabled={!roleId || !bridgeReady} onRefresh={refresh} />
    </header>
    <RoleSemanticMemoryPane query={query} onQuery={(next) => { setQuery(next); setSelectedId(""); }} supportsStructuredFilters list={semantic.list} loading={semantic.listLoading} error={semantic.listError} selectedId={selectedId} onSelect={setSelectedId} detail={semantic.detail} detailLoading={semantic.detailLoading} detailError={semantic.detailError} renderError={(message) => <host.ui.InlineError message={message} />} />
    <MemoryDocumentTabs selected={selected} onSelect={setSelected} />
    <MemoryDocumentPane name={selected} document={documents.documents.find((item) => item.name === selected)} roleId={roleId} bridgeReady={bridgeReady} loading={documents.loading} error={documents.error} renderError={(message) => <host.ui.InlineError message={message} />} />
  </section>;
}

const defaultMemoryUiModule: PluginUiModule = {
  pluginId: "default_memory",
  roleMemory: { component: DefaultMemoryDashboard },
};

export default defaultMemoryUiModule;
