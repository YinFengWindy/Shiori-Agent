import { createContext, useContext, type ReactNode } from "react";
import type { PluginHostServices } from "./contract/hostServices";

/*
 * Runtime API 2.10.0. One context for the whole renderer: the host mounts
 * every plugin contribution under this Provider, and an external plugin's
 * `usePluginHostServices` resolves to this same module through the SDK peer,
 * so both read the services the host put there.
 */
const PluginHostServicesContext = createContext<PluginHostServices | null>(null);

/** Gives an entire plugin UI subtree access to the host services (the host wraps every bound contribution in it). */
export function PluginHostServicesProvider({ services, children }: { services: PluginHostServices; children: ReactNode }) {
  return <PluginHostServicesContext.Provider value={services}>{children}</PluginHostServicesContext.Provider>;
}

/**
 * The host services of the plugin contribution this component renders in —
 * the same object as that contribution's injected `host` prop — so deep
 * components need not pass `host` down. Throws outside a mounted contribution.
 */
export function usePluginHostServices() {
  const services = useContext(PluginHostServicesContext);
  if (!services) throw new Error("插件 UI 缺少宿主服务");
  return services;
}
