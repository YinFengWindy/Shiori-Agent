import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { useAccountAction } from "./useAccountAction";

test("account action refreshes the created identity only after success and clears retry errors", async () => {
  const changed: Array<string | undefined> = [];
  let fail = true;
  function Probe() {
    const { busy, error, run } = useAccountAction((accountId) => changed.push(accountId));
    return <><output>{busy ? "busy" : error || "idle"}</output>
      <button type="button" onClick={() => void run(async () => {
        if (fail) throw new Error("invalid token");
        return "telegram:1";
      })}>保存</button></>;
  }
  const view = await mountTestComponent(<Probe />);
  try {
    await act(async () => view.container.querySelector("button")?.click());
    assert.equal(view.container.querySelector("output")?.textContent, "invalid token");
    assert.deepEqual(changed, []);
    fail = false;
    await act(async () => view.container.querySelector("button")?.click());
    assert.equal(view.container.querySelector("output")?.textContent, "idle");
    assert.deepEqual(changed, ["telegram:1"]);
  } finally { await view.cleanup(); }
});
