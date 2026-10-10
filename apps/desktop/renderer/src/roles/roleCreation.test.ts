import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { RoleProfileDraft } from "../shared/types";
import { buildRoleCreationRequest, createRoleFromDraft } from "./roleCreation";

const form = { name: "小诗", description: "", systemPrompt: "安静、细心" };
describe("role creation", () => {
  it("sends the selected avatar in the same manual creation request", () => {
    assert.deepEqual(buildRoleCreationRequest({ ...form, avatarSource: "avatar.png" }), {
      method: "roles.create", payload: { name: form.name, description: "", system_prompt: form.systemPrompt, avatar_source: "avatar.png" },
    });
  });
  it("sends all structured fields when manually creating a role", () => {
    const profile: RoleProfileDraft = {
      character: { profile: "夜间档案管理员", personality: "细心、耐心", behavior_rules: "  保持诚实  ", response_constraints: "每次回复一句", nickname: "小栞" },
    };
    assert.deepEqual(buildRoleCreationRequest({ ...form, name: "  小栞  ", systemPrompt: "旧规则", profile, avatarSource: "avatar.png" }), {
      method: "roles.create",
      payload: { name: "小栞", description: "", system_prompt: "保持诚实", profile, avatar_source: "avatar.png" },
    });
  });
  it("accepts any nonblank structured field as the manual creation prompt", () => {
    for (const field of ["profile", "personality", "behavior_rules", "response_constraints"] as const) {
      const profile: RoleProfileDraft = { character: { [field]: "  角色资料  " } };
      assert.deepEqual(buildRoleCreationRequest({ ...form, systemPrompt: "", profile }), {
        method: "roles.create",
        payload: { name: form.name, description: "", system_prompt: "角色资料", profile },
      });
    }
  });
  it("rejects empty manual profile fields even if an obsolete prompt remains in the draft", () => {
    const profiles: RoleProfileDraft[] = [
      { character: {} },
      { character: { profile: "  ", personality: "\n", behavior_rules: "\t", response_constraints: "", nickname: "昵称不能代替资料" } },
    ];
    for (const profile of profiles) {
      assert.throws(() => buildRoleCreationRequest({ ...form, profile }), /角色名称和系统提示词不能为空/);
    }
    assert.throws(() => buildRoleCreationRequest({ ...form, systemPrompt: "  " }), /角色名称和系统提示词不能为空/);
    assert.throws(() => buildRoleCreationRequest({ ...form, name: "  " }), /角色名称和系统提示词不能为空/);
  });
  it("distinguishes keeping, replacing, and removing an imported avatar", () => {
    const imported = { ...form, importId: "import-1" };
    for (const avatarSource of [undefined, "new.png", ""]) {
      const { payload } = buildRoleCreationRequest({ ...imported, avatarSource });
      assert.ok("overrides" in payload);
      assert.equal(payload.overrides.avatar_source, avatarSource);
      assert.equal("avatar_source" in payload.overrides, avatarSource !== undefined);
    }
  });
  it("rejects persistence failures without pretending a role was created", async () => {
    await assert.rejects(createRoleFromDraft(form, async () => ({ id: "1", type: "response", method: "roles.create", payload: {}, error: { code: "asset_error", message: "头像保存失败" } })), /头像保存失败/);
    await assert.rejects(createRoleFromDraft(form, async () => ({ id: "1", type: "response", method: "roles.create", payload: {}, error: null })), /缺少角色信息/);
  });
});
