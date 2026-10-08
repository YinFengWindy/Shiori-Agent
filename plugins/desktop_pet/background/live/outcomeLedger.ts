import { cancelledResult, type OutputResult } from "../replyOutput";
import type { LiveReplyIds, LiveReplyOutcome } from "./contract";

/** One received live reply awaiting its single outcome. */
export type LedgerEntry = { readonly ids: LiveReplyIds; reported: boolean };

/**
 * Enforces "exactly one outcome per received live reply": each entry is
 * reported at most once, and closing answers every open entry `cancelled`
 * before reporting stops for good.
 */
export class LiveOutcomeLedger {
  private closedForGood = false;
  private readonly open = new Set<LedgerEntry>();

  constructor(private readonly report: (outcome: LiveReplyOutcome) => Promise<unknown>) {}

  /** True once closed; nothing is reported afterwards. */
  get closed() { return this.closedForGood; }

  /** Opens an entry for a reply that will be answered later. */
  track(ids: LiveReplyIds): LedgerEntry {
    const entry = { ids, reported: false };
    this.open.add(entry);
    return entry;
  }

  /** Reports `entry` unless it was already answered or the ledger is closed. */
  async answer(entry: LedgerEntry, bubble: OutputResult, speech: OutputResult): Promise<void> {
    this.open.delete(entry);
    if (entry.reported || this.closedForGood) return;
    entry.reported = true;
    await this.report({ ...entry.ids, bubble, speech });
  }

  /** Answers every open entry `cancelled`, then stops reporting. */
  async close(): Promise<void> {
    await Promise.all([...this.open].map((entry) => this.answer(entry, cancelledResult, cancelledResult)));
    this.closedForGood = true;
  }
}
