import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act } from "react";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { shouldGuardRoleEditorLeave, useLeaveGuard } from "./useLeaveGuard";

describe("shouldGuardRoleEditorLeave", () => {
  it("guards only a dirty draft on the role detail or assets page", () => {
    assert.equal(shouldGuardRoleEditorLeave({ kind: "role-detail", roleId: "mira" }, true), true);
    assert.equal(shouldGuardRoleEditorLeave({ kind: "role-assets", roleId: "mira" }, true), true);
    assert.equal(shouldGuardRoleEditorLeave({ kind: "role-detail", roleId: "mira" }, false), false);
    assert.equal(shouldGuardRoleEditorLeave({ kind: "chat" }, true), false);
    assert.equal(shouldGuardRoleEditorLeave({ kind: "roles-list" }, true), false);
  });
});

async function mountGuard(active: boolean) {
  const calls: string[] = [];
  let guard!: ReturnType<typeof useLeaveGuard>;
  function Harness() {
    guard = useLeaveGuard({ active, onDiscard: () => { calls.push("discard"); } });
    return null;
  }
  const view = await mountTestComponent(<Harness />);
  return { view, calls, get guard() { return guard; } };
}

describe("useLeaveGuard", () => {
  it("runs navigation straight through while nothing is unsaved", async () => {
    const harness = await mountGuard(false);
    try {
      await act(async () => harness.guard.guard((target: string) => { harness.calls.push(target); })("chat"));
      assert.deepEqual(harness.calls, ["chat"]);
      assert.equal(harness.guard.confirming, false);
    } finally { await harness.view.cleanup(); }
  });

  it("holds navigation back until the user discards, then discards before navigating", async () => {
    const harness = await mountGuard(true);
    try {
      await act(async () => harness.guard.guard((target: string) => { harness.calls.push(target); })("settings"));
      assert.deepEqual(harness.calls, []);
      assert.equal(harness.guard.confirming, true);
      await act(async () => harness.guard.confirmLeave());
      assert.deepEqual(harness.calls, ["discard", "settings"]);
      assert.equal(harness.guard.confirming, false);
    } finally { await harness.view.cleanup(); }
  });

  it("drops the held navigation when the user keeps editing", async () => {
    const harness = await mountGuard(true);
    try {
      await act(async () => harness.guard.guard(() => { harness.calls.push("chat"); })());
      await act(async () => harness.guard.cancelLeave());
      assert.equal(harness.guard.confirming, false);
      await act(async () => harness.guard.confirmLeave());
      assert.deepEqual(harness.calls, []);
    } finally { await harness.view.cleanup(); }
  });
});
