import { usePluginEnabledState, usePluginRosterLoaded } from "../plugins/usePluginEnabledState";
import { usePluginRpcClient } from "../plugins/usePluginRpcClient";
import { ReadStatusLine } from "../shared/feedback/ReadStatus";
import { memoryStatusText } from "./memoryStatusText";
import { RoleMemoryPage } from "./RoleMemoryPage";

/** Binds the page to default_memory's namespace-scoped RPC client. */
function ConnectedRoleMemoryPage({ pluginId, roleId }: { pluginId: string; roleId: string }) {
  const client = usePluginRpcClient(pluginId);
  return <RoleMemoryPage client={client} roleId={roleId} />;
}

/**
 * Role-detail 「记忆」 tab. Shows default_memory while that plugin is active.
 * The general settings page no longer selects an engine; 7b-3 will follow the
 * actual memory provider.
 */
export function RoleMemoryPanel({ roleId, bridgeReady }: { roleId: string; bridgeReady: boolean }) {
  const isPluginEnabled = usePluginEnabledState();
  const rosterLoaded = usePluginRosterLoaded();

  if (!bridgeReady) return <ReadStatusLine text={memoryStatusText.disconnected} />;
  if (!roleId) return <ReadStatusLine text={memoryStatusText.noRole} />;
  // Until the roster arrives every plugin reads as disabled; don't flash closed.
  if (!rosterLoaded) return <ReadStatusLine text={memoryStatusText.loading} />;
  if (!isPluginEnabled("default_memory")) return <ReadStatusLine text={memoryStatusText.closed} />;
  return <ConnectedRoleMemoryPage key={`default_memory:${roleId}`} pluginId="default_memory" roleId={roleId} />;
}
