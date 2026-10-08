import { usePluginEnabledState, usePluginRosterLoaded } from "../plugins/usePluginEnabledState";
import { usePluginRpcClient } from "../plugins/usePluginRpcClient";
import { InlineError } from "../shared/feedback/InlineError";
import { ReadStatusLine } from "../shared/feedback/ReadStatus";
import { memoryStatusText } from "./memoryStatusText";
import { RoleMemoryPage } from "./RoleMemoryPage";
import { useConfiguredMemoryPlugin } from "./useConfiguredMemoryPlugin";

/** Binds the page to the configured plugin's namespace-scoped RPC client. */
function ConnectedRoleMemoryPage({ pluginId, roleId }: { pluginId: string; roleId: string }) {
  const client = usePluginRpcClient(pluginId);
  return <RoleMemoryPage client={client} roleId={roleId} />;
}

/**
 * Role-detail 「记忆」 tab. Reads only the configured memory plugin; when that
 * plugin is missing or disabled the page is unavailable rather than served by
 * another engine.
 */
export function RoleMemoryPanel({ roleId, bridgeReady }: { roleId: string; bridgeReady: boolean }) {
  const selection = useConfiguredMemoryPlugin(bridgeReady);
  const isPluginEnabled = usePluginEnabledState();
  const rosterLoaded = usePluginRosterLoaded();

  if (!bridgeReady) return <ReadStatusLine text={memoryStatusText.disconnected} />;
  if (!roleId) return <ReadStatusLine text={memoryStatusText.noRole} />;
  if (selection.status === "loading") return <ReadStatusLine text={memoryStatusText.loading} />;
  if (selection.status === "error") return <InlineError message={`记忆设置读取失败：${selection.error}`} />;
  // Until the roster arrives every plugin reads as disabled; don't flash "unavailable".
  if (!rosterLoaded) return <ReadStatusLine text={memoryStatusText.loading} />;
  if (!isPluginEnabled(selection.pluginId)) return <ReadStatusLine text={memoryStatusText.pluginUnavailable} />;
  // A new plugin or role starts a fresh page, so no state or pending read carries over.
  return <ConnectedRoleMemoryPage key={`${selection.pluginId}:${roleId}`} pluginId={selection.pluginId} roleId={roleId} />;
}
