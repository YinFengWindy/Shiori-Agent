import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { setImmediate } from "node:timers/promises";
import { SerialDraftQueue } from "./serialDraftQueue";

describe("SerialDraftQueue", () => {
  it("coalesces edits made while a submission is in flight", async () => {
    let release!: (value: { ok: true; result: string }) => void;
    const calls: string[] = [];
    const queue = new SerialDraftQueue<string, string>({
      isEqual: (a, b) => a === b,
      clone: (draft) => draft,
      attempt: async (draft) => {
        calls.push(draft);
        return new Promise((resolve) => { release = resolve; });
      },
      onApplied: () => undefined,
      onStatus: () => undefined,
    });

    queue.enqueue("first");
    queue.enqueue("obsolete");
    queue.enqueue("second");
    release({ ok: true, result: "first" });
    await setImmediate();

    assert.deepEqual(calls, ["first", "second"]);
  });

  it("keeps a failure that does not resume automatically paused until an explicit retry", async () => {
    const attempts: string[] = [];
    const statuses: string[] = [];
    const queue = new SerialDraftQueue<string, string>({
      isEqual: (a, b) => a === b,
      clone: (draft) => draft,
      attempt: async (draft) => {
        attempts.push(draft);
        return { ok: false, resumesAutomatically: false, message: "boom" };
      },
      onApplied: () => assert.fail("should not apply a failed attempt"),
      onStatus: (phase) => statuses.push(phase),
    });

    queue.enqueue("first");
    await setImmediate();
    queue.enqueue("second");
    await setImmediate();
    assert.deepEqual(attempts, ["first"]);

    queue.retry();
    await setImmediate();
    assert.deepEqual(attempts, ["first", "first"]);
    assert.deepEqual(statuses, ["saving", "error", "saving", "error"]);
  });

  it("keeps trying new edits after a failure that resumes automatically, without an explicit retry", async () => {
    const attempts: string[] = [];
    const queue = new SerialDraftQueue<string, string>({
      isEqual: (a, b) => a === b,
      clone: (draft) => draft,
      attempt: async (draft) => {
        attempts.push(draft);
        return draft === "invalid"
          ? { ok: false, resumesAutomatically: true, message: "invalid" }
          : { ok: true, result: draft };
      },
      onApplied: () => undefined,
      onStatus: () => undefined,
    });

    queue.enqueue("invalid");
    await setImmediate();
    queue.enqueue("corrected");
    await setImmediate();

    assert.deepEqual(attempts, ["invalid", "corrected"]);
  });

  it("reuses the same operation id when retrying the identical failed draft", async () => {
    const operationIds: string[] = [];
    let shouldFail = true;
    const queue = new SerialDraftQueue<string, string>({
      isEqual: (a, b) => a === b,
      clone: (draft) => draft,
      attempt: async (draft, operationId) => {
        operationIds.push(operationId);
        if (shouldFail) return { ok: false, resumesAutomatically: false, message: "boom" };
        return { ok: true, result: draft };
      },
      onApplied: () => undefined,
      onStatus: () => undefined,
    });

    queue.enqueue("first");
    await setImmediate();
    shouldFail = false;
    queue.retry();
    await setImmediate();

    assert.equal(operationIds.length, 2);
    assert.equal(operationIds[0], operationIds[1]);
  });
});


it("debounces consecutive drafts and cancels a reverted pending save", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const calls: string[] = [];
  const phases: string[] = [];
  const queue = new SerialDraftQueue<string, string>({
    debounceMs: 400, isEqual: (a, b) => a === b, clone: (value) => value,
    attempt: async (value) => { calls.push(value); return { ok: true, result: value }; },
    onApplied: () => {}, onStatus: (phase) => phases.push(phase),
  });
  queue.enqueue("a", "saved");
  t.mock.timers.tick(300);
  queue.enqueue("ab", "saved");
  t.mock.timers.tick(300);
  queue.enqueue("ab", "saved"); // Renders of the same draft do not restart its quiet period.
  t.mock.timers.tick(99);
  assert.deepEqual(calls, []);
  assert.equal(phases.at(-1), "saving");
  t.mock.timers.tick(1);
  await setImmediate();
  assert.deepEqual(calls, ["ab"]);
  queue.enqueue("changed", "ab");
  queue.enqueue("ab", "ab");
  t.mock.timers.tick(400);
  assert.deepEqual(calls, ["ab"]);
  assert.equal(phases.at(-1), "idle");
});

it("waits for both the in-flight save and the latest quiet period without announcing saved early", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const calls: string[] = [], phases: string[] = [];
  let complete!: () => void;
  const queue = new SerialDraftQueue<string, string>({
    debounceMs: 400, isEqual: (a, b) => a === b, clone: (value) => value,
    attempt: async (value) => { calls.push(value); await new Promise<void>((resolve) => { complete = resolve; }); return { ok: true, result: value }; },
    onApplied: () => {}, onStatus: (phase) => phases.push(phase),
  });
  queue.enqueue("first"); t.mock.timers.tick(400);
  queue.enqueue("obsolete"); t.mock.timers.tick(200); queue.enqueue("last");
  complete(); await setImmediate();
  assert.deepEqual(calls, ["first"]);
  assert.equal(phases.at(-1), "saving");
  t.mock.timers.tick(399); assert.deepEqual(calls, ["first"]);
  t.mock.timers.tick(1); assert.deepEqual(calls, ["first", "last"]);
  complete(); await setImmediate();
  assert.equal(phases.at(-1), "idle");
});

it("flushes the latest draft on departure, including a draft behind an in-flight save", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const calls: string[] = [];
  let complete!: () => void;
  const queue = new SerialDraftQueue<string, string>({
    debounceMs: 400, isEqual: (a, b) => a === b, clone: (value) => value,
    attempt: async (value) => { calls.push(value); await new Promise<void>((resolve) => { complete = resolve; }); return { ok: true, result: value }; },
    onApplied: () => {}, onStatus: () => {},
  });
  queue.enqueue("first"); queue.flush(); assert.deepEqual(calls, ["first"]);
  queue.enqueue("last"); queue.flush(); assert.deepEqual(calls, ["first"]);
  complete(); await setImmediate(); assert.deepEqual(calls, ["first", "last"]);
  complete(); await setImmediate();
  t.mock.timers.tick(400); assert.deepEqual(calls, ["first", "last"]);
});

it("flush does not bypass an unknown outcome and retry keeps the original operation ID", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const calls: Array<[string, string]> = [];
  let fail = true;
  const queue = new SerialDraftQueue<string, string>({
    debounceMs: 400, isEqual: (a, b) => a === b, clone: (value) => value,
    attempt: async (value, id) => { calls.push([value, id]); if (fail) throw new Error("timeout"); return { ok: true, result: value }; },
    onApplied: () => {}, onStatus: () => {},
  });
  queue.enqueue("first"); queue.flush(); await setImmediate();
  queue.enqueue("last"); queue.flush(); t.mock.timers.tick(400); await setImmediate();
  assert.equal(calls.length, 1);
  fail = false; queue.retry(); await setImmediate();
  assert.deepEqual(calls[1], calls[0]);
  assert.equal(calls[2][0], "last"); assert.notEqual(calls[2][1], calls[0][1]);
});


it("can save a previously acknowledged value again after external persistence changes", async () => {
  const calls: string[] = [];
  const queue = new SerialDraftQueue<string, string>({
    isEqual: (a, b) => a === b, clone: (value) => value,
    attempt: async (value) => { calls.push(value); return { ok: true, result: value }; },
    onApplied: () => {}, onStatus: () => {},
  });
  queue.enqueue("local", "original");
  assert.equal(queue.hasPendingWork, true);
  await setImmediate();
  assert.equal(queue.hasPendingWork, false);
  queue.enqueue("local", "external");
  await setImmediate();
  assert.deepEqual(calls, ["local", "local"]);
});
