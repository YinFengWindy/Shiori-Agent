import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { canSkipOnboardingStep, selectOnboardingScene, selectOnboardingStepStatuses } from "./onboardingSteps";

describe("onboarding steps", () => {
  it("keeps every step visible and marks done / current / upcoming", () => {
    assert.deepEqual(selectOnboardingStepStatuses("role").map((item) => [item.label, item.status]), [
      ["模型", "done"], ["角色", "current"], ["开始", "upcoming"],
    ]);
    assert.deepEqual(selectOnboardingStepStatuses("workspace").map((item) => item.status), ["done", "done", "current"]);
    assert.deepEqual(selectOnboardingStepStatuses(undefined).map((item) => item.status), ["upcoming", "upcoming", "upcoming"]);
  });

  it("tells an unreachable bridge from a failed action", () => {
    assert.equal(selectOnboardingScene({ error: "offline", hasData: false, step: "role" }), "offline");
    assert.equal(selectOnboardingScene({ error: "无法进入", hasData: true, step: "workspace" }), "failed");
    assert.equal(selectOnboardingScene({ error: "", hasData: false, step: undefined }), "loading");
    assert.equal(selectOnboardingScene({ error: "", hasData: true, step: "model" }), "model");
  });

  it("offers skip only while setup remains", () => {
    assert.deepEqual(["model", "role", "workspace", undefined].map((step) => canSkipOnboardingStep(step as never)), [true, true, false, false]);
  });
});
