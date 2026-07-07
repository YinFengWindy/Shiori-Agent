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
    relationship_snapshot: overrides.relationship_snapshot ?? null,
    loneliness_runtime: overrides.loneliness_runtime ?? null,
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
    moodCatalog: overrides.moodCatalog ?? ["平静", "开心"],
    defaultMood: overrides.defaultMood ?? "平静",
    moodIllustrationBindings: overrides.moodIllustrationBindings ?? {},
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
      selectedChatImageKey: "",
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
      selectedChatImageKey: "",
      health: "online",
      sendingSessions: { "role:mira": "mira" },
    });

    assert.equal(viewModel.headerTitle, "正在输入中...");
    assert.equal(viewModel.bridgeReady, true);
  });

  it("keeps duplicate latest images distinct when selection uses the history entry key", () => {
    const session = createSession();
    session.messages = [
      {
        id: "message-1",
        role: "assistant",
        content: "first",
        media: ["D:\\images\\latest.png"],
      },
      {
        id: "message-2",
        role: "assistant",
        content: "second",
        media: ["D:\\images\\latest.png"],
      },
    ];

    const viewModel = buildDesktopViewModel({
      roles: [createRole()],
      activeRoleId: "mira",
      mainView: { kind: "chat" },
      roleForm: createRoleForm(),
      activeIllustration: "",
      activeSession: session,
      selectedChatImageKey: "message-2:0",
      health: "online",
      sendingSessions: {},
    });

    assert.equal(viewModel.selectedChatImageIndex, 1);
    assert.equal(viewModel.selectedChatImagePosition, 2);
    assert.equal(viewModel.selectedChatImageEntry?.messageId, "message-2");
    assert.equal(viewModel.resolvedChatImagePath, "D:\\images\\latest.png");
  });

  it("derives the current mood illustration from session metadata and role bindings", () => {
    const session = createSession();
    session.metadata = {
      role_id: "mira",
      current_mood: "开心",
    };
    const viewModel = buildDesktopViewModel({
      roles: [createRole()],
      activeRoleId: "mira",
      mainView: { kind: "chat" },
      roleForm: createRoleForm({
        moodIllustrationBindings: {
          开心: "D:\\roles\\mira\\happy.png",
        },
      }),
      activeIllustration: "",
      activeSession: session,
      selectedChatImageKey: "",
      health: "online",
      sendingSessions: {},
    });

    assert.equal(viewModel.currentMood, "开心");
    assert.equal(viewModel.moodIllustration, "D:\\roles\\mira\\happy.png");
    assert.match(viewModel.moodIllustrationUrl, /happy\.png/);
  });

  it("resolves mood illustration bindings saved as relative role asset paths", () => {
    const session = createSession();
    session.metadata = {
      role_id: "mira",
      current_mood: "开心",
    };
    const viewModel = buildDesktopViewModel({
      roles: [createRole({
        illustrations: ["assets/roles/mira/happy.png"],
        illustrations_abs: ["D:\\roles\\mira\\happy.png"],
      })],
      activeRoleId: "mira",
      mainView: { kind: "chat" },
      roleForm: createRoleForm({
        moodIllustrationBindings: {
          开心: "assets/roles/mira/happy.png",
        },
      }),
      activeIllustration: "",
      activeSession: session,
      selectedChatImageKey: "",
      health: "online",
      sendingSessions: {},
    });

    assert.equal(viewModel.moodIllustration, "D:\\roles\\mira\\happy.png");
    assert.match(viewModel.moodIllustrationUrl, /happy\.png/);
  });

  it("derives relationship summary, tags, and loneliness value from session metadata first", () => {
    const session = createSession();
    session.metadata = {
      role_id: "mira",
      relationship_snapshot: {
        role_id: "mira",
        role_self_view: "我最近会不自觉地去想你会不会来找我。",
        relation_tags: ["亲近", "怕被冷落"],
        internal_profile: {
          relation_state: {},
          behavior_profile: {},
        },
        source_summary: {},
        generated_at: "2026-07-06T18:00:00+08:00",
        last_attempted_at: "2026-07-06T18:00:00+08:00",
        last_error: "",
      },
      loneliness_runtime: {
        role_id: "mira",
        loneliness_value: 64,
        last_calculated_at: "2026-07-06T18:00:00+08:00",
        last_user_at: "",
        last_proactive_at: "",
        awaiting_reply_after_proactive: false,
        awaiting_reply_since: "",
        last_triggered_at: "",
        cooldown_until: "",
      },
    };

    const viewModel = buildDesktopViewModel({
      roles: [createRole()],
      activeRoleId: "mira",
      mainView: { kind: "chat" },
      roleForm: createRoleForm(),
      activeIllustration: "",
      activeSession: session,
      selectedChatImageKey: "",
      health: "online",
      sendingSessions: {},
    });

    assert.equal(viewModel.roleSelfView, "我最近会不自觉地去想你会不会来找我。");
    assert.deepEqual(viewModel.relationshipTags, ["亲近", "怕被冷落"]);
    assert.equal(viewModel.lonelinessValue, 64);
  });

  it("falls back to the role payload relationship runtime when the session metadata is empty", () => {
    const role = createRole({
      relationship_snapshot: {
        role_id: "mira",
        role_self_view: "我还是会留意你有没有想起我。",
        relation_tags: ["嘴硬", "等你主动"],
        internal_profile: {
          relation_state: {},
          behavior_profile: {},
        },
        source_summary: {},
        generated_at: "2026-07-06T18:00:00+08:00",
        last_attempted_at: "2026-07-06T18:00:00+08:00",
        last_error: "",
      },
      loneliness_runtime: {
        role_id: "mira",
        loneliness_value: 52,
        last_calculated_at: "2026-07-06T18:00:00+08:00",
        last_user_at: "",
        last_proactive_at: "",
        awaiting_reply_after_proactive: false,
        awaiting_reply_since: "",
        last_triggered_at: "",
        cooldown_until: "",
      },
    });

    const viewModel = buildDesktopViewModel({
      roles: [role],
      activeRoleId: "mira",
      mainView: { kind: "chat" },
      roleForm: createRoleForm(),
      activeIllustration: "",
      activeSession: createSession(),
      selectedChatImageKey: "",
      health: "online",
      sendingSessions: {},
    });

    assert.equal(viewModel.roleSelfView, "我还是会留意你有没有想起我。");
    assert.deepEqual(viewModel.relationshipTags, ["嘴硬", "等你主动"]);
    assert.equal(viewModel.lonelinessValue, 52);
  });

  it("drops malformed relationship fields so renderer summaries stay safe", () => {
    const session = createSession();
    session.metadata = {
      role_id: "mira",
      relationship_snapshot: {
        role_id: "mira",
        role_self_view: { text: "bad" },
        relation_tags: ["亲近", { text: "bad" }, "等你主动"],
      },
      loneliness_runtime: {
        role_id: "mira",
        loneliness_value: "61",
      },
    } as unknown as SessionPayload["metadata"];

    const viewModel = buildDesktopViewModel({
      roles: [createRole()],
      activeRoleId: "mira",
      mainView: { kind: "chat" },
      roleForm: createRoleForm(),
      activeIllustration: "",
      activeSession: session,
      selectedChatImageKey: "",
      health: "online",
      sendingSessions: {},
    });

    assert.equal(viewModel.roleSelfView, "");
    assert.deepEqual(viewModel.relationshipTags, ["亲近", "等你主动"]);
    assert.equal(viewModel.lonelinessValue, 61);
  });
});
