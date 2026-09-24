/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { modelEffortLabels, modelEffortOptions } from "./modelEffortLabels";

describe("model effort labels", () => {
  it("names every bridge effort value in Chinese", () => {
    assert.deepEqual(modelEffortLabels, { none: "关闭", low: "低", high: "高", max: "最高" });
  });

  it("orders options from off to strongest", () => {
    assert.deepEqual(modelEffortOptions.map((option) => option.label), ["关闭", "低", "高", "最高"]);
  });
});
