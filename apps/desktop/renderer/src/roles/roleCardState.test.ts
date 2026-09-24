import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { RoleRecord } from "../shared/types";
import { resolveRoleCardCover, selectRoleCardView } from "./roleCardState";

function role(overrides: Partial<RoleRecord> = {}): RoleRecord {
  return {
    id: "mira", name: "mira", description: "  学生会长  ", system_prompt: "", runtime_config: {},
    avatar: null, avatar_abs: null, chat_background: null, chat_background_abs: null,
    illustrations: [], illustrations_abs: [], asset_categories: [], asset_category_bindings: {},
    created_at: "", updated_at: "",
    ...overrides,
  };
}

describe("resolveRoleCardCover", () => {
  it("uses the illustration bound to the default mood first", () => {
    const withMood = role({
      runtime_config: { default_mood: "平静", mood_illustration_bindings: { 平静: "a/calm.png" } },
      illustrations: ["a/calm.png"], illustrations_abs: ["C:/r/a/calm.png"],
      chat_background_abs: "C:/r/a/bg.png",
    });
    assert.equal(resolveRoleCardCover(withMood), "C:/r/a/calm.png");
  });

  it("falls back to the chat background, and to nothing", () => {
    assert.equal(resolveRoleCardCover(role({ chat_background_abs: "C:/r/a/bg.png" })), "C:/r/a/bg.png");
    assert.equal(resolveRoleCardCover(role()), "");
  });

  it("skips a mood binding whose image left the library", () => {
    const stale = role({ runtime_config: { default_mood: "平静", mood_illustration_bindings: { 平静: "a/gone.png" } } });
    assert.equal(resolveRoleCardCover(stale), "");
  });
});

describe("selectRoleCardView", () => {
  it("builds the placeholder data and trims the intro", () => {
    const view = selectRoleCardView(role({ avatar_abs: "C:/r/avatar.png" }), null);
    assert.equal(view.initial, "M");
    assert.equal(view.description, "学生会长");
    assert.equal(view.avatarPath, "C:/r/avatar.png");
    assert.equal(view.pending, null);
  });

  it("reports this card's own pending create/delete only", () => {
    assert.equal(selectRoleCardView(role(), { roleId: "mira", action: "delete" }).pending, "delete");
    assert.equal(selectRoleCardView(role(), { roleId: "other", action: "delete" }).pending, null);
  });
});
