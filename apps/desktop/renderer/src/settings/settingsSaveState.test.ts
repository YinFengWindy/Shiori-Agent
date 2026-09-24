import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  isSettingsSaveCompleted,
  shouldShowSettingsFeedback,
} from "./settingsSaveState.js";

describe("settingsSaveState", () => {
  it("only keeps failures visible", () => {
    assert.equal(shouldShowSettingsFeedback("error", "offline"), true);
    assert.equal(shouldShowSettingsFeedback("saving", "saving"), false);
    assert.equal(shouldShowSettingsFeedback("idle", "saved"), false);
  });
});

describe("isSettingsSaveCompleted", () => {
  it("only fires for a save that finished without error", () => {
    assert.equal(isSettingsSaveCompleted("saving", "idle"), true);
    assert.equal(isSettingsSaveCompleted("saving", "error"), false);
    assert.equal(isSettingsSaveCompleted("idle", "idle"), false);
    assert.equal(isSettingsSaveCompleted("error", "idle"), false);
  });
});
