import { useEffect, useState } from "react";
import {
  nextStartupSplashCheckMs,
  selectStartupSplashPhase,
  startupSplashExitMs,
  type StartupSplashPhase,
} from "./startupSplashPhase";

/**
 * Drives the startup splash from the bridge health: times the current
 * connection attempt (restarted whenever health goes back to "connecting"),
 * remembers that startup is over once the backend has answered, and keeps
 * the last phase on screen for the fade-out. With `enabled` false (the
 * 看板娘 is off) there is no splash at all, as before stage 10.
 */
export function useStartupSplash(health: string, enabled: boolean) {
  const [attemptStartedAt, setAttemptStartedAt] = useState(() => Date.now());
  const [elapsedMs, setElapsedMs] = useState(0);
  const [settled, setSettled] = useState(health === "online");
  const [shownPhase, setShownPhase] = useState<StartupSplashPhase | null>(null);
  const [leaving, setLeaving] = useState(false);

  // A new attempt (first launch, or 「重启连接」) restarts the clock; an answer ends startup.
  useEffect(() => {
    if (health === "online") {
      setSettled(true);
      return;
    }
    if (health === "connecting") {
      setAttemptStartedAt(Date.now());
      setElapsedMs(0);
    }
  }, [health]);

  // Wakes up once per threshold (show, slow) instead of ticking.
  useEffect(() => {
    if (settled) return undefined;
    const next = nextStartupSplashCheckMs(elapsedMs);
    if (next === null) return undefined;
    const timer = window.setTimeout(() => setElapsedMs(Date.now() - attemptStartedAt), Math.max(0, attemptStartedAt + next - Date.now()));
    return () => window.clearTimeout(timer);
  }, [attemptStartedAt, elapsedMs, settled]);

  const phase = enabled ? selectStartupSplashPhase({ health, settled, shown: shownPhase !== null, attemptElapsedMs: elapsedMs }) : null;

  // Remember what was last on screen, so the splash can fade out showing it.
  useEffect(() => {
    if (phase) {
      setShownPhase(phase);
      setLeaving(false);
    } else if (shownPhase && !leaving) {
      setLeaving(true);
    }
  }, [leaving, phase, shownPhase]);

  useEffect(() => {
    if (!leaving) return undefined;
    const timer = window.setTimeout(() => {
      setShownPhase(null);
      setLeaving(false);
    }, startupSplashExitMs);
    return () => window.clearTimeout(timer);
  }, [leaving]);

  return {
    /** What the splash shows, or null when it is not mounted. */
    phase: phase ?? shownPhase,
    /** The backend answered: the splash is fading out. */
    leaving: !phase && leaving,
  };
}
