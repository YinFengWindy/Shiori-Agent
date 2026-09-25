/** System idle time (seconds) at which the user counts as away from the desktop. Fixed by design. */
export const desktopPresenceIdleThresholdSeconds = 10 * 60;

/** OS signals that decide desktop presence. */
export type DesktopPresenceSignals = {
  locked: boolean;
  idleSeconds: number;
};

/** The user is present only while the screen is unlocked and input is recent. */
export function isDesktopPresent({ locked, idleSeconds }: DesktopPresenceSignals): boolean {
  return !locked && idleSeconds < desktopPresenceIdleThresholdSeconds;
}

/** Injected OS reads and backend delivery used by {@link DesktopPresenceTracker}. */
export type DesktopPresenceTrackerOptions = {
  readIdleSeconds: () => number;
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
 * report; a backend restart puts it back there (see {@link backendRestarted}).
 */
export class DesktopPresenceTracker {
  private locked = false;
  private backendPresent = true;
  private reporting = false;

  constructor(private readonly options: DesktopPresenceTrackerOptions) {}

  /** Records a lock-screen / unlock-screen transition and reports any resulting change. */
  async setLocked(locked: boolean): Promise<void> {
    this.locked = locked;
    await this.sync();
  }

  /** Re-reads idle time; called periodically because the OS has no idle event. */
  async poll(): Promise<void> {
    await this.sync();
  }

  /** A fresh backend process holds its default again, so the next differing state must be re-sent. */
  backendRestarted(): void {
    this.backendPresent = true;
  }

  private async sync(): Promise<void> {
    // One report at a time; the running one re-syncs when it lands, so a change
    // observed meanwhile is not lost and reports stay ordered.
    if (this.reporting) return;
    const present = isDesktopPresent({
      locked: this.locked,
      idleSeconds: this.options.readIdleSeconds(),
    });
    if (present === this.backendPresent || !this.options.canReport()) return;
    this.reporting = true;
    try {
      await this.options.report(present);
    } catch (error) {
      // The mirror keeps the old value, so the next poll retries the report.
      this.options.onReportFailed(error);
      return;
    } finally {
      this.reporting = false;
    }
    this.backendPresent = present;
    await this.sync();
  }
}
