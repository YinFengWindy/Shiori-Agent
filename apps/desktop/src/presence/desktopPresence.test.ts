import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  DesktopPresenceTracker,
  desktopPresenceIdleThresholdSeconds,
  presenceFromIdleState,
  type DesktopIdleState,
} from "./desktopPresence.js";

function harness() {
  const state: { idle: DesktopIdleState; canReport: boolean; fail: boolean } = {
    idle: "active",
    canReport: true,
    fail: false,
  };
  const reports: boolean[] = [];
  const failures: unknown[] = [];
  const tracker = new DesktopPresenceTracker({
    readIdleState: () => state.idle,
    canReport: () => state.canReport,
    report: async (present) => {
      if (state.fail) throw new Error("bridge_exit");
      reports.push(present);
    },
    onReportFailed: (error) => failures.push(error),
  });
  return { state, reports, failures, tracker };
}

/** A tracker whose first report stays in flight until `release` is called. */
function heldHarness() {
  const reports: boolean[] = [];
  let release: () => void = () => {};
  const idle: { state: DesktopIdleState } = { state: "active" };
  const tracker = new DesktopPresenceTracker({
    readIdleState: () => idle.state,
    canReport: () => true,
    report: async (present) => {
      reports.push(present);
      if (reports.length === 1) await new Promise<void>((resolve) => { release = resolve; });
    },
    onReportFailed: () => assert.fail("no failure expected"),
  });
  return { reports, idle, tracker, release: () => release() };
}

/**
 * A tracker whose reports each wait until `land(i)` writes them into a modelled
 * backend, the way a request queued behind bridge startup lands late.
 */
function backendHarness() {
  const backend: { value: boolean } = { value: true };
  const idle: { state: DesktopIdleState } = { state: "active" };
  const pending: Array<{ present: boolean; resolve: () => void; landed: boolean }> = [];
  const tracker = new DesktopPresenceTracker({
    readIdleState: () => idle.state,
    canReport: () => true,
    report: (present) =>
      new Promise<void>((resolve) => {
        pending.push({ present, resolve, landed: false });
      }),
    onReportFailed: () => assert.fail("no failure expected"),
  });
  const flush = () => new Promise<void>((done) => setImmediate(done));
  /** Writes report `index` into the backend, then lets the tracker react. */
  const land = async (index: number) => {
    const report = pending[index];
    assert.ok(report && !report.landed, `report ${index} is in flight`);
    report.landed = true;
    backend.value = report.present;
    report.resolve();
    await flush();
  };
  /** Lands every report that follow-up syncs issue, in order, until none is left. */
  const settle = async () => {
    for (let index = pending.findIndex((item) => !item.landed); index >= 0; index = pending.findIndex((item) => !item.landed)) {
      await land(index);
    }
  };
  return { backend, idle, pending, tracker, flush, land, settle };
}

describe("presenceFromIdleState", () => {
  it("is present only while active; locked or idle past the threshold is away", () => {
    assert.equal(desktopPresenceIdleThresholdSeconds, 600);
    assert.equal(presenceFromIdleState("active"), true);
    assert.equal(presenceFromIdleState("idle"), false);
    assert.equal(presenceFromIdleState("locked"), false);
    assert.equal(presenceFromIdleState("unknown"), null, "an unknown OS answer invents no presence");
  });
});

describe("DesktopPresenceTracker", () => {
  it("reports lock and unlock immediately", async () => {
    const { reports, tracker } = harness();
    await tracker.setLocked(true);
    await tracker.setLocked(false);
    assert.deepEqual(reports, [false, true]);
  });

  it("reports idle crossing the threshold and resumed activity on poll", async () => {
    const { state, reports, tracker } = harness();
    await tracker.poll();
    assert.deepEqual(reports, [], "active is the backend default");
    state.idle = "idle";
    await tracker.poll();
    state.idle = "active";
    await tracker.poll();
    assert.deepEqual(reports, [false, true]);
  });

  it("corrects a lock that was already in place or whose event was missed", async () => {
    const { state, reports, tracker } = harness();
    state.idle = "locked";
    await tracker.poll();
    assert.deepEqual(reports, [false]);
  });

  it("stays away after a lock event even if a poll still reads active, until unlock", async () => {
    const { state, reports, tracker } = harness();
    await tracker.setLocked(true);
    state.idle = "active";
    await tracker.poll();
    assert.deepEqual(reports, [false], "an active read between lock and unlock is ignored");
    await tracker.setLocked(false);
    assert.deepEqual(reports, [false, true]);
  });

  it("unlock restores presence even after a poll read locked", async () => {
    const { state, reports, tracker } = harness();
    state.idle = "locked";
    await tracker.setLocked(true);
    await tracker.poll();
    await tracker.setLocked(false);
    assert.deepEqual(reports, [false, true]);
  });

  it("keeps the last known state when the OS answers unknown", async () => {
    const { state, reports, tracker } = harness();
    await tracker.setLocked(true);
    state.idle = "unknown";
    await tracker.poll();
    assert.deepEqual(reports, [false]);
  });

  it("does not re-report an unchanged state", async () => {
    const { state, reports, tracker } = harness();
    await tracker.poll();
    await tracker.setLocked(false);
    assert.deepEqual(reports, [], "present equals the backend's pre-report default");
    await tracker.setLocked(true);
    state.idle = "locked";
    await tracker.poll();
    state.idle = "idle";
    await tracker.poll();
    await tracker.setLocked(true);
    assert.deepEqual(reports, [false], "lock then idle is still one away state");
  });

  it("retries a failed or skipped report on the next sync", async () => {
    const { state, reports, failures, tracker } = harness();
    state.idle = "locked";
    state.canReport = false;
    await tracker.setLocked(true);
    assert.deepEqual(reports, []);
    state.canReport = true;
    state.fail = true;
    await tracker.poll();
    assert.equal(failures.length, 1);
    state.fail = false;
    await tracker.poll();
    assert.deepEqual(reports, [false]);
  });

  it("syncs the current away state to a freshly ready backend at once", async () => {
    const { state, reports, tracker } = harness();
    state.idle = "locked";
    await tracker.setLocked(true);
    await tracker.backendReady();
    assert.deepEqual(reports, [false, false]);
  });

  it("reports the current state to a freshly ready backend even when present", async () => {
    const { reports, tracker } = harness();
    await tracker.backendReady();
    assert.deepEqual(reports, [true], "what a new backend holds is unknown, so it is always told");
  });

  it("delivers a change observed during an in-flight report once it lands", async () => {
    const { reports, tracker, release } = heldHarness();
    const first = tracker.setLocked(true);
    await tracker.setLocked(false);
    assert.deepEqual(reports, [false], "one report at a time");
    release();
    await first;
    assert.deepEqual(reports, [false, true]);
  });

  it("a report issued during startup that lands on the new backend first is overwritten by the current state", async () => {
    const { backend, pending, tracker, flush, land, settle } = backendHarness();
    // Locked during startup: report A waits for readiness inside the bridge client.
    const a = tracker.setLocked(true);
    // Unlocked before ready: A is still in flight, so nothing new is sent yet.
    const unlocked = tracker.setLocked(false);
    const ready = tracker.backendReady();
    await flush();
    assert.deepEqual(pending.map((item) => item.present), [false, true], "ready re-sends even the default value");
    await land(0);
    assert.equal(backend.value, false, "A reached the new backend");
    await settle();
    await Promise.all([a, unlocked, ready]);
    assert.equal(backend.value, true, "the backend ends at the real state");
  });

  it("a report issued during startup that lands on the new backend last triggers a re-sync", async () => {
    const { backend, pending, tracker, flush, land, settle } = backendHarness();
    const a = tracker.setLocked(true);
    const unlocked = tracker.setLocked(false);
    const ready = tracker.backendReady();
    await flush();
    await land(1);
    // A overwrites the new backend with away after the current report landed.
    await land(0);
    assert.equal(backend.value, false);
    await settle();
    await Promise.all([a, unlocked, ready]);
    assert.equal(backend.value, true, "the stale landing re-sent the real state");
    assert.deepEqual(pending.map((item) => item.present), [false, true, true]);
  });

  it("after a stale landing the next change is still reported", async () => {
    const { backend, idle, tracker, flush, land, settle } = backendHarness();
    const a = tracker.setLocked(true);
    idle.state = "locked";
    const ready = tracker.backendReady();
    await flush();
    await land(0);
    await settle();
    await Promise.all([a, ready]);
    assert.equal(backend.value, false);
    idle.state = "active";
    const unlocked = tracker.setLocked(false);
    await flush();
    await settle();
    await unlocked;
    assert.equal(backend.value, true);
  });
});
