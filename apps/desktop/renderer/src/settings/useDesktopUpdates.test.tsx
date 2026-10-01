import assert from "node:assert/strict";
import test from "node:test";
import { act } from "react";
import type { DesktopUpdateApi, DesktopUpdateState } from "../../../src/updateContract.js";
import { mountTestComponent } from "@shiori/sdk/testing";
import { useDesktopUpdates } from "./useDesktopUpdates";

test("a late initial snapshot cannot overwrite a newer update event and subscriptions are cleaned up", async () => {
  const view = await mountTestComponent(null);
  let completeSnapshot!: (state: DesktopUpdateState) => void;
  let notify!: (state: DesktopUpdateState) => void;
  let unsubscribed = false;
  const snapshot: DesktopUpdateState = { revision: 0, currentVersion: "0.2.0", phase: "idle", latestVersion: null, progress: 0, error: null };
  const api: DesktopUpdateApi = {
    getState: () => new Promise((resolve) => { completeSnapshot = resolve; }),
    check: async () => snapshot,
    install: async () => undefined,
    onState: (listener) => { notify = listener; return () => { unsubscribed = true; }; },
  };
  Object.defineProperty(window, "miraDesktop", { configurable: true, value: { updates: api } });
  function Harness() {
    const { state } = useDesktopUpdates();
    return <output>{state?.phase}</output>;
  }
  try {
    await view.render(<Harness />);
    await act(async () => notify({ ...snapshot, revision: 2, phase: "downloaded" }));
    await act(async () => completeSnapshot(snapshot));
    assert.equal(view.container.textContent, "downloaded");
  } finally {
    await view.cleanup();
  }
  assert.equal(unsubscribed, true);
});
