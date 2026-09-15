/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { RoleFormState, RoleRecord, SessionPayload } from "../shared/types";
import { resolveCurrentMood, resolveCurrentThought, resolveMoodIllustration } from "./roleMoodSelectors";

function createRole(overrides: Partial<RoleRecord> = {}): RoleRecord {
  return {
    id: overrides.id ?? "mira",
    name: overrides.name ?? "Mira",
    description: overrides.description ?? "",
    system_prompt: overrides.system_prompt ?? "prompt",
    runtime_config: overrides.runtime_config ?? {},
    avatar: overrides.avatar ?? null,
    avatar_abs: overrides.avatar_abs ?? null,
    chat_background: overrides.chat_background ?? null,
    chat_background_abs: overrides.chat_background_abs ?? "D:\\bg\\fallback.png",
    illustrations: overrides.illustrations ?? [],
    illustrations_abs: overrides.illustrations_abs ?? ["D:\\bg\\fallback.png"],
    asset_categories: [{ id: "default", name: "默认", allow_role_send: false }],
    asset_category_bindings: {},
    created_at: overrides.created_at ?? "",
    updated_at: overrides.updated_at ?? "",
  };
}

function createRoleForm(overrides: Partial<RoleFormState> = {}): RoleFormState {
  return {
    name: overrides.name ?? "Mira",
    description: overrides.description ?? "",
    systemPrompt: overrides.systemPrompt ?? "prompt",
    nsfwMemoryEnabled: overrides.nsfwMemoryEnabled ?? false,
    pluginSettings: overrides.pluginSettings ?? {},
    avatarSource: overrides.avatarSource ?? "",
    illustrationSources: overrides.illustrationSources ?? [],
    removedIllustrations: overrides.removedIllustrations ?? [],
    moodCatalog: overrides.moodCatalog ?? ["平静", "开心"],
    defaultMood: overrides.defaultMood ?? "平静",
    moodIllustrationBindings: overrides.moodIllustrationBindings ?? {},
    voiceEnabled: overrides.voiceEnabled ?? true,
    voiceProvider: overrides.voiceProvider ?? "minimax",
    voiceOwnership: overrides.voiceOwnership ?? "external",
    voiceId: overrides.voiceId ?? "",
    voiceName: overrides.voiceName ?? "",
    voiceSpeed: overrides.voiceSpeed ?? 1,
    voiceMoodEmotions: overrides.voiceMoodEmotions ?? {},
    pendingVoiceAssetDeletes: overrides.pendingVoiceAssetDeletes ?? [],
  };
}

function createSession(metadata: Record<string, unknown>): SessionPayload {
  return {
    key: "role:mira",
    created_at: "",
    updated_at: "",
    last_consolidated: 0,
    metadata,
    messages: [],
  };
}

describe("roleMoodSelectors", () => {
  it("keeps formal thought independent of later relationship snapshots", () => {
    const session = createSession({ current_thought: "我终于放心了。" });
    session.metadata.relationship_snapshot = {
      role_id: "mira", role_self_view: "我来自旧快照。", relation_tags: [],
      internal_profile: { relation_state: {}, behavior_profile: {} }, source_summary: {},
      generated_at: "", last_attempted_at: "", last_error: "",
    };
    assert.equal(resolveCurrentThought(session, createRole()), "我终于放心了。");
    session.metadata.relationship_snapshot.role_self_view = "我来自刚生成的长期快照。";
    assert.equal(resolveCurrentThought(session, createRole()), "我终于放心了。");
    delete session.metadata.current_thought;
    assert.equal(resolveCurrentThought(session, createRole()), "我来自刚生成的长期快照。");
  });

  it("ignores stale role session and form data during a chat role switch", () => {
    const session = createSession({ role_id: "mira", current_mood: "开心", current_thought: "我属于Mira。" });
    const role = createRole({ id: "yin", runtime_config: { default_mood: "平静", mood_illustration_bindings: { 平静: "D:/yin/calm.png" } } });
    const roleForm = createRoleForm({ defaultMood: "开心", moodIllustrationBindings: { 平静: "D:/mira/calm.png", 开心: "D:/mira/happy.png" } });
    assert.equal(resolveCurrentThought(session, role), "");
    assert.equal(resolveCurrentMood({ activeSession: session, detailRole: role, roleForm, useRoleForm: false }), "平静");
    assert.equal(resolveMoodIllustration({ activeSession: session, detailRole: role, roleForm, useRoleForm: false }), "D:/yin/calm.png");
  });
  it("prefers current session mood over default mood", () => {
    assert.equal(
      resolveCurrentMood({
        activeSession: createSession({ current_mood: "开心" }),
        detailRole: createRole(),
        roleForm: createRoleForm(),
      }),
      "开心",
    );
  });

  it("resolves the illustration bound to the current mood", () => {
    assert.equal(
      resolveMoodIllustration({
        activeSession: createSession({ current_mood: "开心" }),
        detailRole: createRole({
          illustrations: ["assets/roles/mira/happy.png"],
          illustrations_abs: ["D:\\roles\\mira\\happy.png"],
        }),
        roleForm: createRoleForm({
          moodIllustrationBindings: {
            开心: "assets/roles/mira/happy.png",
          },
        }),
      }),
      "D:\\roles\\mira\\happy.png",
    );
  });

  it("keeps an absolute bound illustration path when it is already renderer-ready", () => {
    assert.equal(
      resolveMoodIllustration({
        activeSession: createSession({ current_mood: "开心" }),
        detailRole: createRole(),
        roleForm: createRoleForm({
          moodIllustrationBindings: {
            开心: "D:\\roles\\mira\\happy.png",
          },
        }),
      }),
      "D:\\roles\\mira\\happy.png",
    );
  });

  it("returns an empty string when the current mood has no bound illustration", () => {
    assert.equal(
      resolveMoodIllustration({
        activeSession: createSession({ current_mood: "警觉" }),
        detailRole: createRole(),
        roleForm: createRoleForm({
          defaultMood: "平静",
          moodIllustrationBindings: {
            平静: "D:\\roles\\mira\\calm.png",
          },
        }),
      }),
      "",
    );
  });
});
