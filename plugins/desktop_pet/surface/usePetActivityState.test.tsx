import assert from "node:assert/strict";
import test from "node:test";
import { act } from "react";
import type { SurfaceRoleActivity } from "@yinfengwindy/shiori-sdk";
import { createFakeSurfaceHandle, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { usePetActivityState, petNotificationAnimationMs } from "./usePetActivityState";

test("typed activity waves before waiting, resets on rebind, and releases its subscription", async (context) => {
  context.mock.timers.enable({ apis: ["setTimeout"] });
  const listeners = new Set<(activity: SurfaceRoleActivity | null) => void>();
  const surface = createFakeSurfaceHandle({ onRoleActivity: (listener) => {
    listeners.add(listener);
    return () => { listeners.delete(listener); };
  } });
  function Harness() {
    const state = usePetActivityState(surface, "idle");
    return <div data-state={state} />;
  }
  const view = await mountTestComponent(<Harness />);
  const current = () => view.container.firstElementChild?.getAttribute("data-state");
  const emit = async (activity: SurfaceRoleActivity | null) => {
    await act(async () => { for (const listener of listeners) listener(activity); });
  };
  try {
    await emit({ roleId: "a", sessionKey: "role:a", phase: "waiting", notify: true });
    assert.equal(current(), "waving");
    await act(async () => { context.mock.timers.tick(petNotificationAnimationMs); });
    assert.equal(current(), "waiting");
    await emit(null);
    assert.equal(current(), "idle");
    await emit({ roleId: "b", sessionKey: "role:b", phase: "running", notify: false });
    assert.equal(current(), "running", "previous role's waiting state must not dominate");
    await emit({ roleId: "b", sessionKey: "role:b", phase: "waiting", notify: true });
    await emit(null);
    await act(async () => { context.mock.timers.tick(petNotificationAnimationMs); });
    assert.equal(current(), "idle", "a retired notification timer must not restore old activity");
  } finally {
    await view.cleanup();
    context.mock.timers.reset();
  }
  assert.equal(listeners.size, 0);
});
