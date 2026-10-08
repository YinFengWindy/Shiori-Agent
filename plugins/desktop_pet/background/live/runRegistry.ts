/**
 * Live runs seen and cancelled under the current pet role, so a late reply of
 * a cancelled run is rejected instead of shown. Bounded: only the most recent
 * runs are remembered, which is all a single live session ever needs.
 */
export class LiveRunRegistry {
  private seen: string[] = [];
  private cancelled: string[] = [];

  constructor(private readonly limit = 32) {}

  /** Records a run that has shown a reply. */
  see(runId: string) { this.seen = remember(this.seen, runId, this.limit); }

  /** Marks one run, or every seen run when omitted, as cancelled. */
  cancel(runId?: string) {
    for (const id of runId === undefined ? this.seen : [runId]) this.cancelled = remember(this.cancelled, id, this.limit);
  }

  isCancelled(runId: string) { return this.cancelled.includes(runId); }

  /** Forgets everything; called when the pet's role changes. */
  reset() { this.seen = []; this.cancelled = []; }
}

function remember(list: string[], runId: string, limit: number) {
  return list.includes(runId) ? list : [...list, runId].slice(-limit);
}
