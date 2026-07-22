/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { RoleRecord } from "../shared/types";
import {
  buildRoleProactiveConfig,
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
    channel_bindings: [],
    proactive: {
      enabled: false,
      target_channel: "",
      target_chat_id: "",
      profile: "quiet",
      overrides: { loneliness: { threshold: 0.7 } },
      agent: { model: "agent-model", max_steps: 12, content_limit: 3, web_fetch_max_chars: 4000 },
      drift: { enabled: true, max_steps: 8, min_interval_hours: 6 },
    },
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

  it("keeps desktop-pet enablement inside the saved role form", () => {
    const role = createRole();
    const form = createRoleFormFromRole(role);

    assert.equal(form.desktopPetEnabled, false);
    assert.equal(isRoleFormDirty({ ...form, desktopPetEnabled: true }, role), true);
  });

  it("reads and compares role-owned proactive settings", () => {
    const role = createRole();
    const form = createRoleFormFromRole(role);

    assert.equal(form.proactiveProfile, "quiet");
    assert.equal(form.proactiveAgentModel, "agent-model");
    assert.equal(form.proactiveDriftEnabled, true);
    assert.equal(isRoleFormDirty(form, role), false);
    assert.equal(isRoleFormDirty({ ...form, proactiveProfile: "daily" }, role), true);
  });

  it("preserves proactive overrides when building an update payload", () => {
    const role = createRole();
    const form = createRoleFormFromRole(role);

    assert.deepEqual(buildRoleProactiveConfig(role, form), role.proactive);
    assert.deepEqual(
      buildRoleProactiveConfig(role, { ...form, proactiveEnabled: true }).overrides,
      { loneliness: { threshold: 0.7 } },
    );
  });
});
