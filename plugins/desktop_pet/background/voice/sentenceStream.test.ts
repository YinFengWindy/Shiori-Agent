import assert from "node:assert/strict";
import { test } from "node:test";
import { SentenceStream } from "./sentenceStream";

test("a reader waits for more sentences until final, close or abort ends the reply", async () => {
  const stream = new SentenceStream(); const abort = new AbortController();
  const first = stream.next(abort.signal);
  stream.add(["一。"], false);
  assert.equal(await first, "一。");
  const waiting = stream.next(abort.signal);
  stream.add(["二。"], true);
  assert.equal(await waiting, "二。");
  assert.equal(await stream.next(abort.signal), null, "final and drained");

  const closed = new SentenceStream(); const pending = closed.next(abort.signal);
  closed.close(); assert.equal(await pending, null);

  const aborted = new SentenceStream(); const blocked = aborted.next(abort.signal);
  abort.abort(); assert.equal(await blocked, null);
});
