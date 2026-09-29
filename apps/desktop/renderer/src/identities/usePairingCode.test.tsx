import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { mockableWindowTimers, mountTestComponent } from "../shared/testing/domTestHarness";
import { usePairingCode } from "./usePairingCode";

const start = Date.parse("2026-09-29T08:00:00Z");

function Probe() {
  const pairing = usePairingCode();
  return <>
    <button type="button" onClick={() => void pairing.create()}>生成</button>
    <output>{pairing.code ? `${pairing.code} ${pairing.remainingMs}` : "none"}</output>
  </>;
}

test("a created code counts down to its expiry and then disappears; creating again replaces it", async (t) => {
  t.mock.timers.enable({ apis: ["setInterval", "Date"], now: start });
  const codes = ["ABCD2345", "WXYZ6789"];
  const view = await mountTestComponent(<Probe />, { windowGlobals: { ...mockableWindowTimers, miraDesktop: {
    invoke: async ({ method }: { method: string }) => ({ id: "r", type: "response", method, error: null, payload: {
      code: codes.shift(), expires_at: new Date(Date.now() + 10_000).toISOString().replace("Z", "+00:00"),
    } }),
  } } });
  const text = () => view.container.querySelector("output")?.textContent;
  const tick = (ms: number) => act(async () => t.mock.timers.tick(ms));
  try {
    await act(async () => view.container.querySelector("button")?.click());
    assert.equal(text(), "ABCD2345 10000");
    await tick(3000);
    assert.equal(text(), "ABCD2345 7000");
    await act(async () => view.container.querySelector("button")?.click());
    assert.equal(text(), "WXYZ6789 10000");
    await tick(9000);
    assert.equal(text(), "WXYZ6789 1000");
    await tick(1000);
    assert.equal(text(), "none");
  } finally { await view.cleanup(); }
});
