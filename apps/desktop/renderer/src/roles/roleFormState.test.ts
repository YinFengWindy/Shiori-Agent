/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { RoleRecord } from "@yinfengwindy/shiori-sdk";
import {
  buildRoleRuntimeConfig,
  createRoleFormFromRole,
  isRoleFormDirty,
} from "./roleFormState";

function createRole(runtime_config: Record<string, unknown> = {}): RoleRecord {
  return {
    id: "mira",
    name: "Mira",
    description: "",
    system_prompt: "prompt",
    runtime_config,
    avatar: null,
    avatar_abs: null,
    chat_background: null,
    chat_background_abs: null,
    illustrations: [],
    illustrations_abs: [],
    asset_categories: [{ id: "default", name: "默认", allow_role_send: false }],
    asset_category_bindings: {},
    created_at: "",
    updated_at: "",
  };
}

describe("roleFormState", () => {
  it("reads a default-off natural chat preference and tracks independent role edits", () => {
    const disabled = createRole();
    const enabled = { ...createRole({ natural_chat_enabled: true }), id: "other" };
    const disabledForm = createRoleFormFromRole(disabled);
    const enabledForm = createRoleFormFromRole(enabled);
    assert.equal(disabledForm.naturalChatEnabled, false);
    assert.equal(enabledForm.naturalChatEnabled, true);
    assert.equal(isRoleFormDirty(disabledForm, disabled), false);
    assert.equal(isRoleFormDirty({ ...disabledForm, naturalChatEnabled: true }, disabled), true);
    assert.equal(isRoleFormDirty(enabledForm, enabled), false);
    assert.equal(isRoleFormDirty({ ...enabledForm, naturalChatEnabled: false }, enabled), true);
    assert.deepEqual(createRoleFormFromRole(disabled), disabledForm);
  });

  for (const enabled of [false, true]) {
    it(`persists natural chat=${enabled} across save/reopen and mood-asset edits`, () => {
      const role = createRole({ natural_chat_enabled: !enabled, dialogue_model_effort: "high" });
      const form = { ...createRoleFormFromRole(role), naturalChatEnabled: enabled };
      const runtime_config = buildRoleRuntimeConfig(role, form);
      assert.equal(runtime_config.natural_chat_enabled, enabled);
      assert.equal(runtime_config.dialogue_model_effort, "high");
      const reopened = { ...role, runtime_config };
      assert.deepEqual(createRoleFormFromRole(reopened), form);
      assert.equal(isRoleFormDirty(form, reopened), false);
      const assetConfig = buildRoleRuntimeConfig(reopened, { ...form, moodIllustrationBindings: { 平静: "roles/assets/mira/portrait.png" } });
      assert.equal(assetConfig.natural_chat_enabled, enabled);
      assert.equal(role.runtime_config.natural_chat_enabled, !enabled);
    });
  }

  it("keeps the structured profile in the detail draft and tracks its edits", () => {
    const role = {
      ...createRole(),
      profile: {
        character: {
          profile: "A meticulous archivist.",
          personality: "Calm and precise.",
          behavior_rules: "Keep focus.",
        },
      },
    };
    const form = createRoleFormFromRole(role);

    assert.deepEqual(form.profile, role.profile);
    assert.equal(isRoleFormDirty(form, role), false);
    assert.equal(isRoleFormDirty({
      ...form,
      profile: {
        ...form.profile,
        character: { ...form.profile?.character, personality: "Warm and precise." },
      },
    }, role), true);
  });

});
