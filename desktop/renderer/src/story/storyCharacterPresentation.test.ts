/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { RoleRecord } from "../shared/types";
import { createStoryDetails } from "./testFixtures";
import { resolveStoryCharacterIllustration } from "./storyCharacterPresentation";

function createRole(overrides: Partial<Pick<RoleRecord, "avatar_abs" | "illustrations" | "illustrations_abs" | "runtime_config">> = {}) {
  return {
    avatar_abs: overrides.avatar_abs ?? "D:\\roles\\mira\\avatar.png",
    illustrations: overrides.illustrations ?? ["assets/roles/mira/happy.png", "assets/roles/mira/calm.png"],
    illustrations_abs: overrides.illustrations_abs ?? ["D:\\roles\\mira\\happy.png", "D:\\roles\\mira\\calm.png"],
    runtime_config: overrides.runtime_config ?? {},
  } satisfies Pick<RoleRecord, "avatar_abs" | "illustrations" | "illustrations_abs" | "runtime_config">;
}

describe("resolveStoryCharacterIllustration", () => {
  it("prefers the Story snapshot default mood binding over the avatar", () => {
    const story = createStoryDetails({
      roleSnapshot: {
        id: "role-1",
        illustrations: ["assets/roles/mira/happy.png", "assets/roles/mira/calm.png"],
        runtime_config: {
          default_mood: "平静",
          mood_illustration_bindings: { 平静: "assets/roles/mira/calm.png" },
        },
      },
    });

    assert.equal(resolveStoryCharacterIllustration(createRole(), story.roleSnapshot), "D:\\roles\\mira\\calm.png");
  });

  it("falls back to the first role illustration and then the avatar", () => {
    const story = createStoryDetails({ roleSnapshot: { id: "role-1" } });
    assert.equal(resolveStoryCharacterIllustration(createRole(), story.roleSnapshot), "D:\\roles\\mira\\happy.png");
    assert.equal(resolveStoryCharacterIllustration(createRole({ illustrations_abs: [] }), story.roleSnapshot), "D:\\roles\\mira\\avatar.png");
  });
});
