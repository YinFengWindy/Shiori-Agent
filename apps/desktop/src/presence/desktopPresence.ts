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
 * report; every freshly ready backend puts it back there (see {@link backendReady}).
 */
export class DesktopPresenceTracker {
  /** Lock state from lock-screen / unlock-screen events; overrides an `active` idle read. */
  private lockedByEvent = false;
  /** Last known presence from the OS idle state (`unknown` leaves it untouched). */
  private idlePresent = true;
  private backendPresent = true;
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

  /** A newly ready backend holds its default again, so the current state is synced to it right away. */
  async backendReady() {
    this.backendSession += 1;
    this.backendPresent = true;
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
    // The backend was replaced while this was in flight; it no longer holds this value.
    if (session !== this.backendSession) return;
    this.backendPresent = present;
    await this.sync();
  }
}
