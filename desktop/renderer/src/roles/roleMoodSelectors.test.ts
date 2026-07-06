/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { RoleFormState, RoleRecord, SessionPayload } from "../shared/types";
import { resolveCurrentMood, resolveMoodIllustration } from "./roleMoodSelectors";

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
    avatarSource: overrides.avatarSource ?? "",
    illustrationSources: overrides.illustrationSources ?? [],
    removedIllustrations: overrides.removedIllustrations ?? [],
    moodCatalog: overrides.moodCatalog ?? ["平静", "开心"],
    defaultMood: overrides.defaultMood ?? "平静",
    moodIllustrationBindings: overrides.moodIllustrationBindings ?? {},
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
        activeIllustration: "",
        previewIllustrations: ["D:\\roles\\mira\\fallback.png"],
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
        activeIllustration: "",
        previewIllustrations: ["D:\\roles\\mira\\fallback.png"],
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
        activeIllustration: "D:\\roles\\mira\\active.png",
        previewIllustrations: ["D:\\roles\\mira\\fallback.png"],
      }),
      "",
    );
  });
});
