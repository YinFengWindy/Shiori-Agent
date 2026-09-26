import { useCallback, useState } from "react";
import type { PluginRoleMemoryComponentProps, PluginUiModule } from "../../../apps/desktop/renderer/src/plugins/pluginUiModuleContract";
import { MemoryDocumentPane, MemoryDocumentTabs, MemoryRefreshButton } from "../../../apps/desktop/renderer/src/shared/memory/RoleMemoryDocumentParts";
import { useRoleMemoryDocuments } from "../../../apps/desktop/renderer/src/shared/memory/useRoleMemoryDocuments";
import type { RoleMemoryDocument, RoleMemoryDocumentsPayload } from "../../../apps/desktop/renderer/src/shared/types";

/** Default memory plugin's role-detail Dashboard. */
export function DefaultMemoryDashboard({ roleId, bridgeReady, client, host }: PluginRoleMemoryComponentProps) {
  const [selected, setSelected] = useState<RoleMemoryDocument["name"]>("SELF.md");
  const read = useCallback((id: string) => client.call<RoleMemoryDocumentsPayload>("roles.memory.documents", { role_id: id }), [client]);
  const state = useRoleMemoryDocuments(roleId, bridgeReady, read);
  return <section className="grid gap-5" aria-label="角色记忆" data-testid="role-memory-panel">
    <header className="flex items-center justify-between gap-3">
      <h2 className="m-0 text-title-sm text-ink">默认记忆</h2>
      <MemoryRefreshButton disabled={!roleId || !bridgeReady} onRefresh={state.refresh} />
    </header>
    <MemoryDocumentTabs selected={selected} onSelect={setSelected} />
    <MemoryDocumentPane name={selected} document={state.documents.find((item) => item.name === selected)} roleId={roleId} bridgeReady={bridgeReady} loading={state.loading} error={state.error} renderError={(message) => <host.ui.InlineError message={message} />} />
  </section>;
}

const defaultMemoryUiModule: PluginUiModule = {
  pluginId: "default_memory",
  roleMemory: { component: DefaultMemoryDashboard },
};

export default defaultMemoryUiModule;
