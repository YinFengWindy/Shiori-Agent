import type { WebContentsDidStartNavigationEventParams } from "electron";

/** Window lifecycle subset needed to revoke document-scoped native resources. */
export type NativeLifecycleSource = {
  on(name: "did-start-navigation", listener: (details: WebContentsDidStartNavigationEventParams) => void): unknown;
  on(name: "render-process-gone" | "destroyed", listener: () => void): unknown;
};

/** Same-document navigation preserves resources; reload, crash and closure revoke every token. */
export function bindNativeDocumentLifecycle(source: NativeLifecycleSource, revoke: () => void) {
  source.on("did-start-navigation", (details) => { if (details.isMainFrame && !details.isSameDocument) revoke(); });
  source.on("render-process-gone", revoke);
  source.on("destroyed", revoke);
}
