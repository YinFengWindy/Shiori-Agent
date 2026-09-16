import { randomUUID } from "node:crypto";
import type { WebContents, WebContentsDidStartNavigationEventParams } from "electron";
import type { DesktopBridgeClient } from "../bridge/bridgeClient.js";

/** Attributes contexts to a document and releases them before its successor opens. */
export function createPluginCommunicationLifecycle(bridge: DesktopBridgeClient) {
  const watched = new WeakMap<WebContents, { renderer: string; cleanup: Promise<void> }>();
  return async (sender: WebContents, request: { method: string; payload: Record<string, unknown> }) => {
    if (request.method !== "plugins.communication.open") return request;
    let document = watched.get(sender);
    if (!document) {
      document = { renderer: randomUUID(), cleanup: Promise.resolve() };
      watched.set(sender, document);
      const state = document;
      const disconnect = () => {
        const renderer = state.renderer;
        // WebContents survives reloads. Capture the departed document's token so
        // delayed cleanup can never disconnect contexts opened by its successor.
        state.renderer = randomUUID();
        state.cleanup = state.cleanup.then(async () => {
          if (!bridge.isRunning()) return;
          await bridge.invoke({ method: "plugins.communication.disconnect", payload: { renderer } });
        });
        void state.cleanup.catch((error: unknown) => console.error("[plugin-communication] renderer cleanup failed", error));
      };
      const navigate = (details: WebContentsDidStartNavigationEventParams) => {
        if (details.isMainFrame && !details.isSameDocument) disconnect();
      };
      const exit = () => {
        sender.removeListener("did-start-navigation", navigate);
        sender.removeListener("destroyed", exit);
        sender.removeListener("render-process-gone", disconnect);
        watched.delete(sender);
        disconnect();
      };
      sender.on("did-start-navigation", navigate);
      sender.once("destroyed", exit);
      sender.on("render-process-gone", disconnect);
    }
    const renderer = document.renderer;
    // The provider must have released its previous registration before setup
    // in the new document can register the same background method.
    await document.cleanup;
    if (watched.get(sender) !== document || document.renderer !== renderer) {
      throw new Error("plugin communication document was replaced");
    }
    return { ...request, payload: { ...request.payload, renderer } };
  };
}
