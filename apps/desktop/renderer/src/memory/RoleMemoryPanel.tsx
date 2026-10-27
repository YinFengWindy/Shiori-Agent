import { useEffect, useState } from "react";
import { errorMessage } from "@yinfengwindy/shiori-sdk";
import { createPluginBridgeClient } from "../plugins/pluginBridgeClient";
import { usePluginEnabledState, usePluginRosterLoaded } from "../plugins/usePluginEnabledState";
import { usePluginRpcClient } from "../plugins/usePluginRpcClient";
import { ReadError, ReadStatusLine } from "../shared/feedback/ReadStatus";
import { memoryStatusText } from "./memoryStatusText";
import { RoleMemoryPage } from "./RoleMemoryPage";

/** Binds the page to the provider plugin's namespace-scoped RPC client. */
function ConnectedRoleMemoryPage({ pluginId, roleId }: { pluginId: string; roleId: string }) {
  const client = usePluginRpcClient(pluginId);
  return <RoleMemoryPage client={client} roleId={roleId} />;
}

type ProviderPhase =
  | { kind: "loading" }
  | { kind: "ready"; pluginId: string | null }
  | { kind: "error"; message: string };

/**
 * Role-detail 「记忆」 tab. Follows the ACTIVE plugin that provides
 * MEMORY_ENGINE. No provider means semantic memory is off.
 */
export function RoleMemoryPanel({ roleId, bridgeReady }: { roleId: string; bridgeReady: boolean }) {
  const rosterPredicate = usePluginEnabledState();
  const rosterLoaded = usePluginRosterLoaded();
  const [attempt, setAttempt] = useState(0);
  const [phase, setPhase] = useState<ProviderPhase>({ kind: "loading" });

  useEffect(() => {
    if (!bridgeReady || !rosterLoaded) return;
    let cancelled = false;
    setPhase({ kind: "loading" });
    void createPluginBridgeClient().memoryProvider().then(
      (pluginId) => {
        if (!cancelled) setPhase({ kind: "ready", pluginId });
      },
      (error: unknown) => {
        if (!cancelled) setPhase({ kind: "error", message: errorMessage(error) });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [bridgeReady, rosterLoaded, rosterPredicate, attempt]);

  if (!bridgeReady) return <ReadStatusLine text={memoryStatusText.disconnected} />;
  if (!roleId) return <ReadStatusLine text={memoryStatusText.noRole} />;
  if (!rosterLoaded || phase.kind === "loading") return <ReadStatusLine text={memoryStatusText.loading} />;
  if (phase.kind === "error") {
    return <ReadError error={phase.message} onRetry={() => setAttempt((current) => current + 1)} />;
  }
  if (phase.pluginId === null) return <ReadStatusLine text={memoryStatusText.closed} />;
  return <ConnectedRoleMemoryPage key={`${phase.pluginId}:${roleId}`} pluginId={phase.pluginId} roleId={roleId} />;
}
