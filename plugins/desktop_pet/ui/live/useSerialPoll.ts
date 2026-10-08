import { useEffect } from "react";
import { useLatestRef } from "@yinfengwindy/shiori-sdk";

/**
 * Calls `tick` every `intervalMs` while `active`, one call at a time: the
 * next wait starts only after the previous call settled, so a slow answer
 * never overlaps the next request. Turning `active` off or unmounting stops
 * the loop; a call already in flight finishes but schedules nothing more.
 * `tick` handles its own errors and may switch `active` off.
 */
export function useSerialPoll(active: boolean, intervalMs: number, tick: () => Promise<void>) {
  const latestTick = useLatestRef(tick);
  useEffect(() => {
    if (!active) return undefined;
    let running = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const schedule = () => {
      timer = setTimeout(() => {
        void latestTick.current().finally(() => { if (running) schedule(); });
      }, intervalMs);
    };
    schedule();
    return () => {
      running = false;
      clearTimeout(timer);
    };
  }, [active, intervalMs, latestTick]);
}
