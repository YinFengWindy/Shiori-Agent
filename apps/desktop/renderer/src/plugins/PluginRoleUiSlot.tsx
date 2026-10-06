import { pluginRoleUiRegistry } from "./pluginFeatureRegistry";
import { usePluginEnabledState } from "./usePluginEnabledState";
import { usePluginRpcClient } from "./usePluginRpcClient";
import type { PluginRoleUiProps, PluginRoleUiContribution } from "@yinfengwindy/shiori-sdk";
import { useEffect, useState } from "react";
import { createRoleUiDirtyLease } from "./pluginRoleUiDirty";

/** Mounts independent role editors without exposing mutable host drafts or a save callback. */
export function PluginRoleUiSlot({ role, disabled }: Pick<PluginRoleUiProps, "role" | "disabled">) {
  const enabled = usePluginEnabledState();
  return pluginRoleUiRegistry.list().filter((entry) => enabled(entry.pluginId)).map((entry) => (
    <PrivateRoleEditor key={`${entry.pluginId}:${role?.id ?? "new"}`} entry={entry} role={role} disabled={disabled} />
  ));
}

function PrivateRoleEditor({ entry, role, disabled }: { entry: PluginRoleUiContribution & { pluginId: string } } & Pick<PluginRoleUiProps, "role" | "disabled">) {
  const client = usePluginRpcClient(entry.pluginId);
  const [lease] = useState(() => createRoleUiDirtyLease(role?.id ?? ""));
  useEffect(() => { lease.activate(); return () => lease.dispose(); }, [lease]);
  return <entry.Component roleId={role?.id ?? null} role={role} client={client} disabled={disabled} onDirtyChange={lease.set} />;
}
