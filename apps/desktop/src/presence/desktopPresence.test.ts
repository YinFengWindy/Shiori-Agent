import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  DesktopPresenceTracker,
  desktopPresenceIdleThresholdSeconds,
  isDesktopPresent,
} from "./desktopPresence.js";

function harness() {
  const state = { idleSeconds: 0, canReport: true, fail: false };
  const reports: boolean[] = [];
  const failures: unknown[] = [];
  const tracker = new DesktopPresenceTracker({
    readIdleSeconds: () => state.idleSeconds,
    canReport: () => state.canReport,
    report: async (present) => {
      if (state.fail) throw new Error("bridge_exit");
      reports.push(present);
    },
    onReportFailed: (error) => failures.push(error),
  });
  return { state, reports, failures, tracker };
}

describe("isDesktopPresent", () => {
  it("is present only while unlocked and idle below ten minutes", () => {
    assert.equal(desktopPresenceIdleThresholdSeconds, 600);
    assert.equal(isDesktopPresent({ locked: false, idleSeconds: 0 }), true);
    assert.equal(isDesktopPresent({ locked: false, idleSeconds: 599 }), true);
    assert.equal(isDesktopPresent({ locked: false, idleSeconds: 600 }), false, "reaching the threshold is away");
    assert.equal(isDesktopPresent({ locked: true, idleSeconds: 0 }), false, "a locked screen is away");
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
    state.idleSeconds = 599;
    await tracker.poll();
    assert.deepEqual(reports, [], "still present, the backend default");
    state.idleSeconds = 600;
    await tracker.poll();
    state.idleSeconds = 3;
    await tracker.poll();
    assert.deepEqual(reports, [false, true]);
  });

  it("does not re-report an unchanged state", async () => {
    const { state, reports, tracker } = harness();
    await tracker.poll();
    await tracker.setLocked(false);
    assert.deepEqual(reports, [], "present equals the backend's pre-report default");
    await tracker.setLocked(true);
    state.idleSeconds = 900;
    await tracker.poll();
    await tracker.setLocked(true);
    assert.deepEqual(reports, [false], "lock then idle is still one away state");
  });

  it("stays away while locked even when idle time resets", async () => {
    const { state, reports, tracker } = harness();
    await tracker.setLocked(true);
    state.idleSeconds = 0;
    await tracker.poll();
    assert.deepEqual(reports, [false]);
  });

  it("retries a failed or skipped report on the next sync", async () => {
    const { state, reports, failures, tracker } = harness();
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

  it("re-sends away after a backend restart resets it to present", async () => {
    const { reports, tracker } = harness();
    await tracker.setLocked(true);
    tracker.backendRestarted();
    await tracker.poll();
    assert.deepEqual(reports, [false, false]);
  });

  it("delivers a change observed during an in-flight report once it lands", async () => {
    let release: () => void = () => {};
    const reports: boolean[] = [];
    const tracker = new DesktopPresenceTracker({
      readIdleSeconds: () => 0,
      canReport: () => true,
      report: async (present) => {
        reports.push(present);
        if (reports.length === 1) await new Promise<void>((resolve) => { release = resolve; });
      },
      onReportFailed: () => assert.fail("no failure expected"),
    });
    const first = tracker.setLocked(true);
    await tracker.setLocked(false);
    assert.deepEqual(reports, [false], "one report at a time");
    release();
    await first;
    assert.deepEqual(reports, [false, true]);
  });
});
