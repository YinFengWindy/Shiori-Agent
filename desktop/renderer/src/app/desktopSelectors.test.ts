/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { buildDesktopViewModel } from "./desktopSelectors";
import type { RoleFormState, RoleRecord, SessionPayload } from "../shared/types";

function createRole(overrides: Partial<RoleRecord> = {}): RoleRecord {
  return {
    id: overrides.id ?? "mira",
    name: overrides.name ?? "Mira",
    description: overrides.description ?? "",
    system_prompt: overrides.system_prompt ?? "prompt",
    runtime_config: overrides.runtime_config ?? {},
    avatar: overrides.avatar ?? null,
    avatar_abs: overrides.avatar_abs ?? "D:\\avatars\\mira.png",
    chat_background: overrides.chat_background ?? null,
    chat_background_abs: overrides.chat_background_abs ?? "D:\\bg\\mira.png",
    illustrations: overrides.illustrations ?? [],
    illustrations_abs: overrides.illustrations_abs ?? ["D:\\bg\\mira.png"],
    created_at: overrides.created_at ?? "2026-07-04T12:00:00+08:00",
    updated_at: overrides.updated_at ?? "2026-07-04T12:00:00+08:00",
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
  };
}

function createSession(): SessionPayload {
  return {
    key: "role:mira",
    created_at: "2026-07-04T12:00:00+08:00",
    updated_at: "2026-07-04T12:00:00+08:00",
    last_consolidated: 0,
    metadata: { role_id: "mira" },
    messages: [],
  };
}

describe("desktopSelectors", () => {
  it("marks the role form dirty when the editable fields differ from the persisted role", () => {
    const viewModel = buildDesktopViewModel({
      roles: [createRole()],
      activeRoleId: "mira",
      mainView: { kind: "role-detail", roleId: "mira" },
      roleForm: createRoleForm({ description: "changed" }),
      activeIllustration: "",
      activeSession: createSession(),
      selectedChatImagePath: "",
      health: "online",
      sendingSessions: {},
    });

    assert.equal(viewModel.roleFormDirty, true);
  });

  it("derives the visible header title from the visible sending chat session", () => {
    const viewModel = buildDesktopViewModel({
      roles: [createRole()],
      activeRoleId: "mira",
      mainView: { kind: "chat" },
      roleForm: createRoleForm(),
      activeIllustration: "",
      activeSession: createSession(),
      selectedChatImagePath: "",
      health: "online",
      sendingSessions: { "role:mira": "mira" },
    });

    assert.equal(viewModel.headerTitle, "正在输入中...");
    assert.equal(viewModel.bridgeReady, true);
  });
});
