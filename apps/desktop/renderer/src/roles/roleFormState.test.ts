/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { RoleRecord } from "@shiori/plugin-sdk";
import {
  buildRoleProactiveConfig,
  createRoleFormFromRole,
  isRoleFormDirty,
} from "./roleFormState";
import { roleProactiveDefaults } from "./roleProactiveDefaults";

function createRole(runtime_config: Record<string, unknown> = {}): RoleRecord {
  return {
    id: "mira",
    name: "Mira",
    description: "",
    system_prompt: "prompt",
    runtime_config,
    proactive: {
      enabled: false,
      candidates: [],
      profile: "quiet",
      overrides: { loneliness: { threshold: 0.7 } },
      agent: { max_steps: 12, content_limit: 3, web_fetch_max_chars: 4000 },
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

  it("reads and compares role-owned proactive settings", () => {
    const role = createRole();
    const form = createRoleFormFromRole(role);

    assert.equal(form.proactiveProfile, "quiet");
    assert.equal("proactiveAgentModel" in form, false);
    assert.equal("proactiveDriftEnabled" in form, false);
    assert.equal(isRoleFormDirty(form, role), false);
    assert.equal(isRoleFormDirty({ ...form, proactiveProfile: "daily" }, role), true);
  });

  it("preserves proactive overrides when building an update payload", () => {
    const role = createRole();
    const form = createRoleFormFromRole(role);

    assert.deepEqual(buildRoleProactiveConfig(role, form), {
      ...role.proactive,
      agent: { max_steps: 12, content_limit: 3, web_fetch_max_chars: 4000 },
      drift: { max_steps: 8, min_interval_hours: 6 },
    });
    assert.deepEqual(
      buildRoleProactiveConfig(role, { ...form, proactiveEnabled: true }).overrides,
      { loneliness: { threshold: 0.7 } },
    );
  });

  for (const enabled of [false, true]) {
    for (const legacyDriftEnabled of [undefined, false, true]) {
      it(`uses one clean draft switch for enabled=${enabled}, legacy drift=${legacyDriftEnabled}`, () => {
        const role: RoleRecord = {
          ...createRole(),
          proactive: {
            ...createRole().proactive,
            enabled,
            candidates: [],
            drift: { ...(legacyDriftEnabled === undefined ? {} : { enabled: legacyDriftEnabled }), max_steps: 8, min_interval_hours: 6 },
          },
        };
        const form = createRoleFormFromRole(role);
        assert.equal(form.proactiveEnabled, enabled);
        assert.equal("proactiveDriftEnabled" in form, false);
        assert.equal(isRoleFormDirty(form, role), false);
        const changed = { ...form, proactiveEnabled: !enabled };
        assert.equal(isRoleFormDirty(changed, role), true);
        assert.equal(isRoleFormDirty({ ...changed, proactiveEnabled: enabled }, role), false);

        const proactive = buildRoleProactiveConfig(role, changed);
        assert.equal(proactive.enabled, !enabled);
        assert.deepEqual(proactive.drift, { max_steps: 8, min_interval_hours: 6 });
        assert.deepEqual(proactive.overrides, role.proactive?.overrides);
        assert.equal(role.proactive?.drift?.enabled, legacyDriftEnabled, "saving must not mutate the persisted snapshot");
        const reopened = { ...role, proactive };
        assert.deepEqual(createRoleFormFromRole(reopened), changed);
        assert.equal(isRoleFormDirty(createRoleFormFromRole(reopened), reopened), false);
      });
    }
  }

  it("uses one default contract for sparse historical proactive state", () => {
    const role = { ...createRole(), proactive: undefined };
    const form = createRoleFormFromRole(role);

    assert.equal(form.proactiveProfile, roleProactiveDefaults.profile);
    assert.equal(form.proactiveAgentMaxSteps, roleProactiveDefaults.agentMaxSteps);
    assert.equal(form.proactiveAgentContentLimit, roleProactiveDefaults.agentContentLimit);
    assert.equal(form.proactiveAgentWebFetchMaxChars, roleProactiveDefaults.agentWebFetchMaxChars);
    assert.equal(form.proactiveDriftMaxSteps, roleProactiveDefaults.driftMaxSteps);
    assert.equal(form.proactiveDriftMinIntervalHours, roleProactiveDefaults.driftMinIntervalHours);
    assert.equal(isRoleFormDirty(form, role), false);
  });
});
