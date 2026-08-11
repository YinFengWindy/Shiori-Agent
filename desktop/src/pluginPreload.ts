import { contextBridge, ipcRenderer } from "electron";

export type ShioriPluginApi = {
  context(): Promise<{ pluginId: string; contributionId: string }>;
  rpc(method: string, payload?: Record<string, unknown>): Promise<unknown>;
};

const api: ShioriPluginApi = Object.freeze({
  context() {
    return ipcRenderer.invoke("shiori-plugin:context") as Promise<{ pluginId: string; contributionId: string }>;
  },
  rpc(method, payload = {}) {
    return ipcRenderer.invoke("shiori-plugin:rpc", { method, payload });
  },
});

contextBridge.exposeInMainWorld("shioriPlugin", api);
