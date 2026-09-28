import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { deferred } from "../shared/testing/deferred";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { useAccountAction } from "./useAccountAction";

test("account action names the command in flight, refreshes only after success and clears retry errors", async () => {
  const changed: Array<string | undefined> = [];
  let fail = true;
  let gate = deferred<void>();
  function Probe() {
    const { pending, error, run } = useAccountAction((accountId) => changed.push(accountId));
    return <><output>{pending ?? (error || "idle")}</output>
      <button type="button" onClick={() => void run("connect", async () => {
        await gate.promise;
        if (fail) throw new Error("invalid token");
        return "telegram:1";
      })}>保存</button></>;
  }
  const view = await mountTestComponent(<Probe />);
  const output = () => view.container.querySelector("output")?.textContent;
  try {
    await act(async () => view.container.querySelector("button")?.click());
    assert.equal(output(), "connect");
    await act(async () => gate.resolve());
    assert.equal(output(), "invalid token");
    assert.deepEqual(changed, []);
    fail = false;
    gate = deferred<void>();
    await act(async () => view.container.querySelector("button")?.click());
    await act(async () => gate.resolve());
    assert.equal(output(), "idle");
    assert.deepEqual(changed, ["telegram:1"]);
  } finally { await view.cleanup(); }
});
