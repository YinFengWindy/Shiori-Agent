import assert from "node:assert/strict";
import { test } from "node:test";
import { microphoneFailure } from "./microphoneFailure";

for (const [name, text] of [["NotAllowedError", "权限"], ["NotFoundError", "重新选择设备"], ["NotReadableError", "占用"]]) {
  test(`microphone ${name} keeps the specific recovery and technical cause`, () => {
    const failure = microphoneFailure(Object.assign(new Error("native detail"), { name }), "start");
    assert.match(failure.split("\n")[0]!, new RegExp(text!));
    assert.match(failure, /native detail/);
  });
}
