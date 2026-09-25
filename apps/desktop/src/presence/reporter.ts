import { invokeBridgeOrThrow, type BridgeInvoker } from "../bridge/bridgeRequest.js";
import type { BridgeEvent } from "../bridge/shared.js";
import {
  DesktopPresenceTracker,
  desktopPresenceIdleThresholdSeconds,
  type DesktopIdleState,
} from "./desktopPresence.js";

/** How often idle state is re-read; there is no OS idle event to listen to. */
export const desktopPresencePollIntervalMs = 30_000;

/** Bridge method that stores the latest desktop presence in the backend. */
export const desktopPresenceReportMethod = "desktop.presence.report";

/** The part of Electron's `powerMonitor` that presence reads. */
export interface DesktopPresenceMonitor {
  on(event: "lock-screen", listener: () => void): unknown;
  on(event: "unlock-screen", listener: () => void): unknown;
  removeListener(event: "lock-screen", listener: () => void): unknown;
  removeListener(event: "unlock-screen", listener: () => void): unknown;
  getSystemIdleState(idleThreshold: number): DesktopIdleState;
}

/** The part of the desktop bridge client that presence reporting uses. */
export interface DesktopPresenceBridge extends BridgeInvoker {
  isRunning(): boolean;
  on(event: "event", listener: (event: BridgeEvent) => void): unknown;
  off(event: "event", listener: (event: BridgeEvent) => void): unknown;
}

type IntervalHandle = ReturnType<typeof setInterval>;

/** Timer seam so tests can drive polling by hand. */
export type DesktopPresenceTimers = {
  setInterval: (callback: () => void, ms: number) => IntervalHandle;
  clearInterval: (handle: IntervalHandle) => void;
};

const nodeTimers: DesktopPresenceTimers = {
  setInterval: (callback, ms) => setInterval(callback, ms),
  clearInterval: (handle) => clearInterval(handle),
};

/**
 * Keeps the backend informed of desktop presence until disposed.
 *
 * Lock transitions report immediately; idle crossings (and a lock that was
 * already in place or missed) are picked up by polling. Every `bridge.ready`
 * marks a fresh backend, including a graceful restart that emits no `exit`.
 * Reports are skipped while the bridge is down so a report never starts it.
 */
export function startDesktopPresenceReporting(options: {
  monitor: DesktopPresenceMonitor;
  bridge: DesktopPresenceBridge;
  onReportFailed: (error: unknown) => void;
  timers?: DesktopPresenceTimers;
}) {
  const { monitor, bridge, onReportFailed, timers = nodeTimers } = options;
  const tracker = new DesktopPresenceTracker({
    readIdleState: () => monitor.getSystemIdleState(desktopPresenceIdleThresholdSeconds),
    canReport: () => bridge.isRunning(),
    report: async (present) => {
      await invokeBridgeOrThrow(bridge, { method: desktopPresenceReportMethod, payload: { present } });
    },
    onReportFailed,
  });
  const onLock = () => void tracker.setLocked(true);
  const onUnlock = () => void tracker.setLocked(false);
  const onBridgeEvent = (event: BridgeEvent) => {
    if (event.method === "bridge.ready") void tracker.backendReady();
  };
  monitor.on("lock-screen", onLock);
  monitor.on("unlock-screen", onUnlock);
  bridge.on("event", onBridgeEvent);
  const timer = timers.setInterval(() => void tracker.poll(), desktopPresencePollIntervalMs);
  return {
    dispose() {
      timers.clearInterval(timer);
      monitor.removeListener("lock-screen", onLock);
      monitor.removeListener("unlock-screen", onUnlock);
      bridge.off("event", onBridgeEvent);
    },
  };
}
