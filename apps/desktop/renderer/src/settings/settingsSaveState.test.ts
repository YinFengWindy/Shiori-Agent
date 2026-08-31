import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  getSettingsFeedbackTimeoutMs,
  shouldShowSettingsFeedback,
} from "./settingsSaveState.js";

describe("settingsSaveState", () => {
  it("only keeps failures visible", () => {
    assert.equal(getSettingsFeedbackTimeoutMs("error"), 4200);
    assert.equal(getSettingsFeedbackTimeoutMs("idle"), null);
    assert.equal(shouldShowSettingsFeedback("error", "offline"), true);
    assert.equal(shouldShowSettingsFeedback("saving", "saving"), false);
    assert.equal(shouldShowSettingsFeedback("idle", "saved"), false);
  });
});
