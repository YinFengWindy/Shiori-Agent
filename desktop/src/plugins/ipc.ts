import { ipcMain, type IpcMainInvokeEvent } from "electron";
import type { DesktopBridgeClient } from "../bridgeClient.js";
import type { PluginDesktopHost } from "./host.js";

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

/** Registers the only IPC methods exposed to sandboxed plugin pages. */
export function registerPluginHostIpc(host: PluginDesktopHost, bridge: DesktopBridgeClient): void {
  ipcMain.handle("shiori-plugin:context", (event: IpcMainInvokeEvent) => {
    const owner = host.ownerFor(event.sender);
    if (!owner) throw new Error("plugin page is not registered");
    return { pluginId: owner.pluginId, contributionId: owner.contributionId };
  });
  ipcMain.handle("shiori-plugin:rpc", async (event: IpcMainInvokeEvent, request: unknown) => {
    const owner = host.ownerFor(event.sender);
    if (!owner) throw new Error("plugin page is not registered");
    if (!isRecord(request)) throw new Error("plugin RPC request must be an object");
    const method = typeof request.method === "string" ? request.method.trim() : "";
    const payload = request.payload === undefined ? {} : request.payload;
    if (!method || !owner.rpcMethods.has(method)) throw new Error(`plugin RPC method is not declared: ${method}`);
    if (!isRecord(payload)) throw new Error("plugin RPC payload must be an object");
    const response = await bridge.invoke({
      method: "plugins.rpc",
      payload: { plugin_id: owner.pluginId, method, payload },
    });
    if (response.error) throw new Error(response.error.message);
    return response.payload.result;
  });
}
