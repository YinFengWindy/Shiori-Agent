import { invokeBridgePayload, type DesktopInvoke } from "../shared/bridgeInvoke";
import { PluginBridgeError } from "./pluginBridgeError";

/** Validated immutable package identity shown before explicit trust approval. */
export type PluginPackagePreview = {
  token: string;
  id: string;
  name: string;
  version: string;
  previous_version: string;
  action: "install" | "update";
  source_name: string;
  directory: string;
};

/** Calls the restart-only package lifecycle; selection uses the native import boundary. */
export function createPluginPackageClient(invoke?: DesktopInvoke) {
  const call = <T,>(method: string, payload: Record<string, unknown>) => invokeBridgePayload<T>(invoke ?? window.miraDesktop.invoke, method, payload, PluginBridgeError);
  return {
    async pickPackage(candidateId?: string) {
      const [source] = await window.miraDesktop.pickFiles({ namespace: "plugin-packages", filters: [{ name: "插件 ZIP", extensions: ["zip"] }], maxFileBytes: 32 * 1024 * 1024 });
      return source ? call<PluginPackagePreview>("plugins.install.preview", { source, ...(candidateId ? { candidate_id: candidateId } : {}) }) : null;
    },
    confirm: (token: string) => call("plugins.install.confirm", { token, trusted: true }),
    cancel: (token: string) => call("plugins.install.cancel", { token }),
    uninstall: (candidateId: string, deleteData: boolean) => call("plugins.uninstall", { candidate_id: candidateId, delete_data: deleteData, operation_id: crypto.randomUUID() }),
  };
}
