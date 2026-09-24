import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { selectRoleDetailSaveState } from "./roleDetailSaveState";

describe("selectRoleDetailSaveState", () => {
  it("keeps both actions off for an unchanged draft", () => {
    const state = selectRoleDetailSaveState({ dirty: false, saving: false, bridgeReady: true });
    assert.equal(state.canSave, false);
    assert.equal(state.canReset, false);
    assert.equal(state.saveLabel, "保存");
  });

  it("offers save and reset for a changed draft while the bridge is up", () => {
    const state = selectRoleDetailSaveState({ dirty: true, saving: false, bridgeReady: true });
    assert.equal(state.canSave, true);
    assert.equal(state.canReset, true);
  });

  it("allows reset but not save while the bridge is down", () => {
    const state = selectRoleDetailSaveState({ dirty: true, saving: false, bridgeReady: false });
    assert.equal(state.canSave, false);
    assert.equal(state.canReset, true);
  });

  it("shows 保存中 and blocks both actions while a save runs", () => {
    const state = selectRoleDetailSaveState({ dirty: true, saving: true, bridgeReady: true });
    assert.equal(state.canSave, false);
    assert.equal(state.canReset, false);
    assert.equal(state.saving, true);
    assert.equal(state.saveLabel, "保存中…");
  });
});
