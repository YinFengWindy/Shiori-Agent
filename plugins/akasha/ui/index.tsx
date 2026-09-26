import { useCallback } from "react";
import type { PluginRoleMemoryComponentProps, PluginUiModule } from "../../../apps/desktop/renderer/src/plugins/pluginUiModuleContract";
import { RoleMemoryDocumentsView } from "../../../apps/desktop/renderer/src/shared/memory/RoleMemoryDocumentsView";
import { useRoleMemoryDocuments } from "../../../apps/desktop/renderer/src/shared/memory/useRoleMemoryDocuments";
import type { RoleMemoryDocumentsPayload } from "../../../apps/desktop/renderer/src/shared/types";

/** Akasha memory plugin's role-detail Dashboard. */
export function AkashaMemoryDashboard({ roleId, bridgeReady, client }: PluginRoleMemoryComponentProps) {
  const read = useCallback((id: string) => client.call<RoleMemoryDocumentsPayload>("roles.memory.documents", { role_id: id }), [client]);
  const state = useRoleMemoryDocuments(roleId, bridgeReady, read);
  return <RoleMemoryDocumentsView roleId={roleId} bridgeReady={bridgeReady} documents={state.documents} loading={state.loading} error={state.error} onRefresh={state.refresh} />;
}

const akashaUiModule: PluginUiModule = {
  pluginId: "akasha",
  roleMemory: { component: AkashaMemoryDashboard },
};

export default akashaUiModule;
