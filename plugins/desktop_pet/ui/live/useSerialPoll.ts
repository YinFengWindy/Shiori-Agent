import { useEffect, useRef } from "react";
import { useLatestRef } from "@yinfengwindy/shiori-sdk";

/**
 * Calls `tick` every `intervalMs` while `active`, one call at a time: the
 * next wait starts only after the previous call settled, so a slow answer
 * never overlaps the next request. Turning `active` off or unmounting stops
 * the loop; a call already in flight finishes but schedules nothing more, and
 * a loop restarted meanwhile (reopened dialog, new QR) waits for that call
 * before its first wait. `tick` handles its own errors and may switch `active` off.
 */
export function useSerialPoll(active: boolean, intervalMs: number, tick: () => Promise<void>) {
  const latestTick = useLatestRef(tick);
  // The call in flight, shared across loop restarts; not a mirror of rendered state.
  const inFlight = useRef<Promise<void> | null>(null);
  useEffect(() => {
    if (!active) return undefined;
    let running = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const schedule = () => {
      timer = setTimeout(() => {
        const call = latestTick.current();
        inFlight.current = call;
        void call.finally(() => {
          if (inFlight.current === call) inFlight.current = null;
          if (running) schedule();
        });
      }, intervalMs);
    };
    const previous = inFlight.current;
    if (previous) void previous.finally(() => { if (running) schedule(); });
    else schedule();
    return () => {
      running = false;
      clearTimeout(timer);
    };
  }, [active, intervalMs, latestTick]);
}
