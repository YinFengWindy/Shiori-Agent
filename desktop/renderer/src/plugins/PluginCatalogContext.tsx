import { createContext, useContext, type ReactNode } from "react";
import { createPluginCatalog, type PluginCatalog } from "./pluginCatalog";

const PluginCatalogContext = createContext<PluginCatalog>(createPluginCatalog([]));

/** Makes the authoritative loaded-plugin catalog available to fixed contribution slots. */
export function PluginCatalogProvider({ catalog, children }: { catalog: PluginCatalog; children: ReactNode }) {
  return <PluginCatalogContext.Provider value={catalog}>{children}</PluginCatalogContext.Provider>;
}

export function usePluginCatalogContext(): PluginCatalog {
  return useContext(PluginCatalogContext);
}
