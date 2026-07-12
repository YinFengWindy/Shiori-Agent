/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { RoleRecord } from "../shared/types";
import { createRoleFormFromRole, isRoleFormDirty } from "./roleFormState";

function createRole(runtime_config: Record<string, unknown> = {}): RoleRecord {
  return {
    id: "mira",
    name: "Mira",
    description: "",
    system_prompt: "prompt",
    runtime_config,
    channel_bindings: [],
    proactive: { enabled: false, target_channel: "", target_chat_id: "" },
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
  it("defaults automatic scene CG to disabled and reads the role setting", () => {
    assert.equal(createRoleFormFromRole(createRole()).autoSceneCgEnabled, false);
    assert.equal(
      createRoleFormFromRole(
        createRole({ auto_scene_cg_enabled: true }),
      ).autoSceneCgEnabled,
      true,
    );
  });

  it("marks only the automatic scene CG setting as dirty when it changes", () => {
    const role = createRole();
    const form = createRoleFormFromRole(role);

    assert.equal(isRoleFormDirty(form, role), false);
    assert.equal(
      isRoleFormDirty({ ...form, autoSceneCgEnabled: true }, role),
      true,
    );
  });
});
