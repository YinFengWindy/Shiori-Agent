import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { BridgeError } from "@shiori/sdk";
import { mountTestComponent } from "@shiori/sdk/testing";
import { useBusyAction } from "./useBusyAction";

test("failed account and phone actions retain a safe cause while clearing busy state", async () => {
  let action!: ReturnType<typeof useBusyAction>;
  function Probe() { action = useBusyAction(); return null; }
  const view = await mountTestComponent(<Probe />);
  try {
    await act(async () => { assert.equal(await action.run(async () => { throw new BridgeError("操作未完成", "internal_error", { detail: "account locked token=private-value" }); }), false); });
    assert.equal(action.busy, false);
    assert.match(action.error, /account locked/);
    assert.doesNotMatch(action.error, /private-value/);
  } finally { await view.cleanup(); }
});
