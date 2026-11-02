import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { proactiveProfileOptions } from "./roleProactiveOptions";

const values = (devMode: boolean, current: string) => proactiveProfileOptions(devMode, current).map((option) => option.value);

describe("proactiveProfileOptions", () => {
  it("hides 开发验证 outside dev mode", () => {
    assert.deepEqual(values(false, "daily"), ["daily", "quiet"]);
  });

  it("offers 开发验证 in dev mode", () => {
    assert.deepEqual(values(true, "daily"), ["daily", "quiet", "dev_verify"]);
  });

  it("keeps a saved 开发验证 visible so the picker can show and leave it", () => {
    assert.deepEqual(values(false, "dev_verify"), ["daily", "quiet", "dev_verify"]);
  });
});
