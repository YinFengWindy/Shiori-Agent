import type { ipcRenderer } from "electron";
import type { BridgeEvent } from "@shiori/sdk/contract";
import type { PreloadLocalAssetCache } from "../assets/preloadLocalAssetCache.js";
import type { DesktopApi, LocalAssetTransport } from "./shared.js";

/** Shares one preload IPC listener and asset conversion across desktop event subscribers. */
export function createDesktopEventSubscription(
  ipc: {
    on: (...args: Parameters<typeof ipcRenderer.on>) => void;
    off: (...args: Parameters<typeof ipcRenderer.off>) => void;
  },
  localAssets: Pick<PreloadLocalAssetCache, "consume">,
): DesktopApi["onEvent"] {
  const subscriptions = new Set<Parameters<DesktopApi["onEvent"]>[0]>();
  const dispatch = (_event: unknown, payload: unknown) => {
    // Match EventEmitter: additions start next dispatch; removals still receive
    // the current snapshot. Subscriber errors propagate and stop this dispatch.
    const current = [...subscriptions];
    const event = localAssets.consume(payload as LocalAssetTransport<BridgeEvent>);
    for (const listener of current) listener(event);
  };

  return (listener) => {
    // Each call owns an entry, even when the same callback is subscribed twice.
    const subscription = (event: BridgeEvent) => listener(event);
    if (subscriptions.size === 0) ipc.on("desktop:event", dispatch);
    subscriptions.add(subscription);

    return () => {
      if (!subscriptions.delete(subscription)) return;
      if (subscriptions.size === 0) ipc.off("desktop:event", dispatch);
    };
  };
}
