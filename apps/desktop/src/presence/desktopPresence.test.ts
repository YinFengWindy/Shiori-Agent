import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  DesktopPresenceTracker,
  desktopPresenceIdleThresholdSeconds,
  presenceFromIdleState,
  type DesktopIdleState,
} from "./desktopPresence.js";

function harness() {
  const state = { idle: "active" as DesktopIdleState, canReport: true, fail: false };
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
  const idle = { state: "active" as DesktopIdleState };
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

  it("does not report to a freshly ready backend while the user is present", async () => {
    const { reports, tracker } = harness();
    await tracker.backendReady();
    assert.deepEqual(reports, []);
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

  it("ignores a report that lands after the backend was replaced", async () => {
    const { reports, idle, tracker, release } = heldHarness();
    const stale = tracker.setLocked(true);
    idle.state = "locked";
    await tracker.backendReady();
    assert.deepEqual(reports, [false, false], "the new backend gets its own report without waiting");
    release();
    await stale;
    idle.state = "active";
    await tracker.setLocked(false);
    assert.deepEqual(reports, [false, false, true], "the stale landing did not corrupt the mirror");
  });

  it("does not let a stale landing mark the new backend as already away", async () => {
    const { reports, idle, tracker, release } = heldHarness();
    const stale = tracker.setLocked(true);
    // The user came back before the restart: nothing to tell the new backend yet.
    await tracker.setLocked(false);
    idle.state = "active";
    await tracker.backendReady();
    release();
    await stale;
    idle.state = "idle";
    await tracker.poll();
    assert.deepEqual(reports, [false, false], "away is still reported to the new backend");
  });
});
