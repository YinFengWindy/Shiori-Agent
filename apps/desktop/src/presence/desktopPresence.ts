/** System idle time (seconds) at which the user counts as away from the desktop. Fixed by design. */
export const desktopPresenceIdleThresholdSeconds = 10 * 60;

/** What Electron's `powerMonitor.getSystemIdleState(threshold)` answers. */
export type DesktopIdleState = "active" | "idle" | "locked" | "unknown";

/**
 * Maps the OS idle state to presence: a locked screen or input older than the
 * threshold is away. `unknown` yields null — the OS could not tell, so no
 * presence is invented and the last known state stands.
 */
export function presenceFromIdleState(state: DesktopIdleState) {
  if (state === "unknown") return null;
  return state === "active";
}

/** Injected OS read and backend delivery used by {@link DesktopPresenceTracker}. */
export type DesktopPresenceTrackerOptions = {
  /** Reads the idle state against {@link desktopPresenceIdleThresholdSeconds}. */
  readIdleState: () => DesktopIdleState;
  /** False while the backend cannot take a report; the next sync retries. */
  canReport: () => boolean;
  /** Delivers one presence value to the backend, rejecting when it was not accepted. */
  report: (present: boolean) => Promise<void>;
  onReportFailed: (error: unknown) => void;
};

/**
 * Mirrors what the backend believes about desktop presence and reports only changes.
 *
 * The mirror starts at "present" because that is the backend's value before any
 * report. A freshly ready backend makes it unknown (see {@link backendReady}):
 * a report issued while that backend was starting may still land on it.
 */
export class DesktopPresenceTracker {
  /** Lock state from lock-screen / unlock-screen events; overrides an `active` idle read. */
  private lockedByEvent = false;
  /** Last known presence from the OS idle state (`unknown` leaves it untouched). */
  private idlePresent = true;
  /** What the backend holds; null when unknown, which always differs from the current state. */
  private backendPresent: boolean | null = true;
  private reporting = false;
  /** Bumped per backend session so a report sent to a previous one never updates the mirror. */
  private backendSession = 0;

  constructor(private readonly options: DesktopPresenceTrackerOptions) {}

  /** Records a lock-screen / unlock-screen transition and reports any resulting change. */
  async setLocked(locked: boolean) {
    this.lockedByEvent = locked;
    // Unlocking takes user input, so any earlier idle/locked read is stale.
    if (!locked) this.idlePresent = true;
    await this.sync();
  }

  /** Re-reads the OS idle state; called periodically because the OS has no idle event. */
  async poll() {
    const present = presenceFromIdleState(this.options.readIdleState());
    if (present !== null) this.idlePresent = present;
    await this.sync();
  }

  /** Syncs the current state to a newly ready backend right away, whatever it may hold. */
  async backendReady() {
    this.backendSession += 1;
    // Not simply its default: a report issued while it was starting waits for
    // readiness and lands on it after this, carrying a possibly outdated value.
    this.backendPresent = null;
    // A report still in flight belongs to the previous backend; it must not
    // block the first report to this one.
    this.reporting = false;
    await this.poll();
  }

  private async sync() {
    // One report at a time per backend session; the running one re-syncs when
    // it lands, so a change observed meanwhile is not lost and reports stay ordered.
    if (this.reporting) return;
    // Between a lock event and its unlock, an `active` read (the OS may lag in
    // reporting the lock) must not flip the user back to present.
    const present = !this.lockedByEvent && this.idlePresent;
    if (present === this.backendPresent || !this.options.canReport()) return;
    const session = this.backendSession;
    this.reporting = true;
    try {
      await this.options.report(present);
    } catch (error) {
      // The mirror keeps the old value, so the next poll retries the report.
      this.options.onReportFailed(error);
      return;
    } finally {
      if (session === this.backendSession) this.reporting = false;
    }
    if (session !== this.backendSession) {
      // Issued to an earlier session but may have landed on the current backend,
      // overwriting it; forget what it holds and re-sync unless a current
      // report is still in flight (its landing overrides this one).
      this.backendPresent = null;
      await this.sync();
      return;
    }
    this.backendPresent = present;
    await this.sync();
  }
}
