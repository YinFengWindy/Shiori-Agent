import assert from "node:assert/strict";
import { test } from "node:test";
import type { LiveReplyOutcome } from "./contract";
import { LiveOutcomeLedger } from "./outcomeLedger";

test("each entry is answered once, and closing answers the open ones cancelled before going silent", async () => {
  const reports: LiveReplyOutcome[] = [];
  const ledger = new LiveOutcomeLedger(async (outcome) => { reports.push(outcome); });
  const done = ledger.track({ reply_id: "r1", run_id: "run" });
  const open = ledger.track({ reply_id: "r2", run_id: "run" });
  await ledger.answer(done, { status: "succeeded" }, { status: "skipped" });
  await ledger.answer(done, { status: "failed", error: "x" }, { status: "failed", error: "x" });
  await ledger.close();
  await ledger.answer(open, { status: "succeeded" }, { status: "succeeded" });
  await ledger.answer(ledger.track({ reply_id: "r3", run_id: "run" }), { status: "succeeded" }, { status: "succeeded" });
  assert.deepEqual(reports.map(({ reply_id, speech }) => [reply_id, speech.status]), [["r1", "skipped"], ["r2", "cancelled"]]);
  assert.equal(ledger.closed, true);
});
