import { useEffect, useState } from "react";

/** The current time, updated on every minute boundary, for the phone's status bar. */
export function usePhoneClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    let timer = 0;
    // Waking at the next minute boundary (not every 60s from mount) keeps the
    // clock from lagging up to a minute behind the system clock.
    const schedule = () => {
      const current = new Date();
      const untilNextMinute = 60_000 - current.getSeconds() * 1000 - current.getMilliseconds();
      timer = window.setTimeout(() => {
        setNow(new Date());
        schedule();
      }, untilNextMinute);
    };
    schedule();
    return () => window.clearTimeout(timer);
  }, []);
  return now;
}
