import { useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { errorMessage, type PluginHostServices, type PluginRpcClient, type RoleRecord } from "@yinfengwindy/shiori-sdk";
import { DashboardStore } from "./dashboardStore";

/** Own subscriptions only while this view is mounted or its client is current. */
export function useDashboard(client: PluginRpcClient, host: PluginHostServices) {
  const store = useMemo(() => new DashboardStore(client, host), [client, host]);
  const state = useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
  useEffect(() => { void store.start(); return () => store.stop(); }, [store]);
  return { state, store };
}

/** Role names are host data; task ownership stays in the plugin snapshot. */
export function useRoleNames(host: PluginHostServices) {
  const [roles, setRoles] = useState<RoleRecord[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    let request = 0;
    const load = () => { const current = ++request; void host.listRoles().then((value) => { if (active && current === request) { setRoles(value); setError(""); } }, (reason: unknown) => { if (active && current === request) setError(errorMessage(reason)); }); };
    load();
    const off = host.onEvent((event) => { if (["roles.changed", "bridge.ready", "runtime.applied"].includes(event.method)) load(); });
    return () => { active = false; off(); };
  }, [host]);
  return { names: new Map(roles.map((role) => [role.id, role.name])), error };
}
