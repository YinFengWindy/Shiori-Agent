import type { BridgeResponse } from "../bridge/shared.js";
import { DesktopPresenceTracker } from "./desktopPresence.js";

/** How often idle time is re-read; there is no OS idle event to listen to. */
export const desktopPresencePollIntervalMs = 30_000;

/** Bridge method that stores the latest desktop presence in the backend. */
export const desktopPresenceReportMethod = "desktop.presence.report";

type LockEvent = "lock-screen" | "unlock-screen";

/** The part of Electron's `powerMonitor` that presence reads. */
export interface DesktopPresenceMonitor {
  on(event: "lock-screen", listener: () => void): unknown;
  on(event: "unlock-screen", listener: () => void): unknown;
  removeListener(event: "lock-screen", listener: () => void): unknown;
  removeListener(event: "unlock-screen", listener: () => void): unknown;
  getSystemIdleTime(): number;
}

/** The part of the desktop bridge client that presence reporting uses. */
export interface DesktopPresenceBridge {
  invoke(request: { method: string; payload: Record<string, unknown> }): Promise<BridgeResponse>;
  isRunning(): boolean;
  on(event: "exit", listener: () => void): unknown;
  off(event: "exit", listener: () => void): unknown;
}

/** Timer seam so tests can drive polling by hand. */
export type DesktopPresenceTimers = {
  setInterval: (callback: () => void, ms: number) => unknown;
  clearInterval: (handle: unknown) => void;
};

const nodeTimers: DesktopPresenceTimers = {
  setInterval: (callback, ms) => setInterval(callback, ms),
  clearInterval: (handle) => clearInterval(handle as NodeJS.Timeout),
};

/**
 * Keeps the backend informed of desktop presence until disposed.
 *
 * Lock transitions report immediately; idle crossings are noticed by polling.
 * Reports are skipped while the bridge is down so a report never starts it.
 */
export function startDesktopPresenceReporting(options: {
  monitor: DesktopPresenceMonitor;
  bridge: DesktopPresenceBridge;
  onReportFailed: (error: unknown) => void;
  timers?: DesktopPresenceTimers;
}): { dispose(): void } {
  const { monitor, bridge, onReportFailed, timers = nodeTimers } = options;
  const tracker = new DesktopPresenceTracker({
    readIdleSeconds: () => monitor.getSystemIdleTime(),
    canReport: () => bridge.isRunning(),
    report: async (present) => {
      const response = await bridge.invoke({ method: desktopPresenceReportMethod, payload: { present } });
      if (response.error) throw new Error(response.error.message);
    },
    onReportFailed,
  });
  const lockListeners: Record<LockEvent, () => void> = {
    "lock-screen": () => void tracker.setLocked(true),
    "unlock-screen": () => void tracker.setLocked(false),
  };
  const onBridgeExit = () => tracker.backendRestarted();
  monitor.on("lock-screen", lockListeners["lock-screen"]);
  monitor.on("unlock-screen", lockListeners["unlock-screen"]);
  bridge.on("exit", onBridgeExit);
  const timer = timers.setInterval(() => void tracker.poll(), desktopPresencePollIntervalMs);
  return {
    dispose() {
      timers.clearInterval(timer);
      monitor.removeListener("lock-screen", lockListeners["lock-screen"]);
      monitor.removeListener("unlock-screen", lockListeners["unlock-screen"]);
      bridge.off("exit", onBridgeExit);
    },
  };
}
