import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { onboardingReactionLine, onboardingSceneLines, type OnboardingReaction, type OnboardingScene } from "./onboardingScript";

const scenes: OnboardingScene[] = ["model", "role", "workspace", "offline", "failed"];
const reactions: OnboardingReaction[] = ["connectionOk", "connectionFailed", "modelSaveFailed", "avatarPicked", "importFailed", "roleCreateFailed", "skipModel", "skipRole"];

describe("onboarding script", () => {
  it("keeps every line within 40 characters", () => {
    const all = [
      ...scenes.flatMap((scene) => onboardingSceneLines(scene, { greet: true, roleName: "小诗" })),
      ...reactions.map(onboardingReactionLine),
    ];
    for (const line of all) assert.ok([...line.text].length <= 40, line.text);
  });

  it("greets once before the first step and resumes straight at later steps", () => {
    assert.equal(onboardingSceneLines("model", { greet: true, roleName: "" })[0].expression, "smug");
    assert.equal(onboardingSceneLines("model", { greet: true, roleName: "" }).length, 3);
    assert.equal(onboardingSceneLines("model", { greet: false, roleName: "" }).length, 1);
    assert.equal(onboardingSceneLines("role", { greet: true, roleName: "" }).length, 2);
  });

  it("names the created role on the last step", () => {
    assert.match(onboardingSceneLines("workspace", { greet: false, roleName: "小诗" })[0].text, /小诗/);
  });

  it("answers form actions with the agreed expressions", () => {
    assert.equal(onboardingReactionLine("connectionOk").expression, "laugh");
    assert.equal(onboardingReactionLine("connectionFailed").expression, "sad");
    assert.equal(onboardingReactionLine("avatarPicked").expression, "surprised");
    assert.equal(onboardingReactionLine("importFailed").expression, "confused");
    assert.equal(onboardingReactionLine("skipModel").expression, "pout");
  });

  it("says nothing while still connecting", () => {
    assert.deepEqual(onboardingSceneLines("loading", { greet: true, roleName: "" }), []);
  });
});
