/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type {
  BridgeResponse,
  DesktopApi,
  SettingsChannelRoleBinding,
  SettingsFormData,
  SettingsSnapshot,
} from "../../../src/shared.js";
import type { RoleRecord } from "../shared/types.js";
import {
  loadSettingsPageData,
  saveSettingsPageData,
  shouldRetryFailedSettingsLoad,
} from "./settingsPersistence.js";

function createBindings(chatId: string): SettingsChannelRoleBinding[] {
  return [
    {
      channel: "desktop",
      chatId,
      roleId: "mira",
    },
  ];
}

function createSettingsFormData(
  roleBindings: SettingsChannelRoleBinding[],
  overrides: Partial<SettingsFormData["models"]> = {},
): SettingsFormData {
  return {
    models: {
      provider: "openai",
      mainModel: overrides.mainModel ?? "gpt-main",
      mainApiKey: "",
      mainBaseUrl: "",
      enableThinking: false,
      reasoningEffort: "medium",
      multimodal: false,
      fastModel: "gpt-fast",
      fastApiKey: "",
      fastBaseUrl: "",
      agentModel: "gpt-agent",
      agentApiKey: "",
      agentBaseUrl: "",
      vlModel: "gpt-vl",
      vlApiKey: "",
      vlBaseUrl: "",
    },
    channels: {
      telegramToken: "",
      telegramAllowFrom: [],
      qqBotUin: "",
      qqAllowFrom: [],
      qqGroups: [],
      roleBindings,
    },
    memory: {
      enabled: true,
      engine: "default",
      embeddingModel: "",
      embeddingApiKey: "",
      embeddingBaseUrl: "",
      outputDimensionality: "",
    },
    proactive: {
      enabled: false,
      profile: "default",
      targetChannel: "desktop",
      targetChatId: "",
      targetRoleId: "",
      agentMaxSteps: 35,
      agentContentLimit: 5,
      agentWebFetchMaxChars: 8000,
      driftEnabled: false,
      driftMaxSteps: 20,
      driftMinIntervalHours: 3,
    },
    integrations: {
      novelaiEnabled: false,
      novelaiToken: "",
      novelaiNsfwEnabled: false,
      novelaiAddQualityTags: false,
      novelaiUndesiredContentPreset: 0,
      novelaiAutoWritebackRoleAssets: false,
    },
    advanced: {
      systemPrompt: "",
      maxTokens: 4000,
      maxIterations: 10,
      devMode: false,
      memoryWindow: 20,
      searchEnabled: true,
      spawnEnabled: true,
      memoryOptimizerEnabled: false,
      memoryOptimizerIntervalSeconds: 3600,
      pluginsRawToml: "",
    },
  };
}

function createSettingsSnapshot(
  roleBindings: SettingsChannelRoleBinding[],
  overrides: Partial<SettingsFormData["models"]> = {},
): SettingsSnapshot {
  return {
    configPath: "D:\\Coding\\Shiori\\config.toml",
    formData: createSettingsFormData(roleBindings, overrides),
  };
}

function createRole(): RoleRecord {
  return {
    id: "mira",
    name: "Mira",
    description: "",
    system_prompt: "",
    runtime_config: {},
    avatar: null,
    avatar_abs: null,
    chat_background: null,
    chat_background_abs: null,
    illustrations: [],
    illustrations_abs: [],
    created_at: "2026-07-07T00:00:00+08:00",
    updated_at: "2026-07-07T00:00:00+08:00",
  };
}

function createRolesResponse(role: RoleRecord): BridgeResponse {
  return {
    id: "roles-list",
    type: "response",
    method: "roles.list",
    payload: {
      roles: [role],
    },
    error: null,
  };
}

describe("shouldRetryFailedSettingsLoad", () => {
  it("retries once the bridge recovers from a failed settings load", () => {
    assert.equal(
      shouldRetryFailedSettingsLoad({
        bridgeReady: true,
        loadError: "bridge offline",
      }),
      true,
    );
    assert.equal(
      shouldRetryFailedSettingsLoad({
        bridgeReady: false,
        loadError: "bridge offline",
      }),
      false,
    );
  });
});

describe("loadSettingsPageData", () => {
  it("hydrates bridge-backed role bindings into the loaded snapshot", async () => {
    const snapshot = createSettingsSnapshot([]);
    const bindings = createBindings("role:mira");
    const loaded = await loadSettingsPageData({
      readSettings: async () => snapshot,
      readChannelRoleBindings: async () => ({ bindings }),
      invoke: async () => createRolesResponse(createRole()),
    } satisfies Pick<DesktopApi, "invoke" | "readChannelRoleBindings" | "readSettings">);

    assert.deepEqual(loaded.snapshot.formData.channels.roleBindings, bindings);
    assert.equal(loaded.roles[0]?.id, "mira");
  });
});

describe("saveSettingsPageData", () => {
  it("saves config before bindings and preserves unsaved bindings after a binding failure", async () => {
    const calls: string[] = [];
    const currentSnapshot = createSettingsSnapshot(createBindings("role:old"), {
      mainModel: "current-model",
    });
    const draft = createSettingsFormData(createBindings("role:new"), {
      mainModel: "draft-model",
    });
    const persistedSnapshot = createSettingsSnapshot(createBindings("role:old"), {
      mainModel: "saved-model",
    });

    const result = await saveSettingsPageData(
      {
        saveSettings: async () => {
          calls.push("saveSettings");
          return {
            ok: true,
            restart: { ok: true, running: true, lastError: null },
            health: { ok: true, message: "ok" },
          };
        },
        saveChannelRoleBindings: async () => {
          calls.push("saveChannelRoleBindings");
          throw new Error("bindings unavailable");
        },
        readSettings: async () => {
          calls.push("readSettings");
          return persistedSnapshot;
        },
        readChannelRoleBindings: async () => {
          calls.push("readChannelRoleBindings");
          return { bindings: currentSnapshot.formData.channels.roleBindings };
        },
      } satisfies Pick<
        DesktopApi,
        "readChannelRoleBindings" | "readSettings" | "saveChannelRoleBindings" | "saveSettings"
      >,
      draft,
      currentSnapshot,
    );

    assert.deepEqual(calls, [
      "saveSettings",
      "saveChannelRoleBindings",
      "readSettings",
      "readChannelRoleBindings",
    ]);
    assert.equal(result.snapshot.formData.models.mainModel, "saved-model");
    assert.deepEqual(
      result.snapshot.formData.channels.roleBindings,
      currentSnapshot.formData.channels.roleBindings,
    );
    assert.deepEqual(
      result.nextDraft.channels.roleBindings,
      draft.channels.roleBindings,
    );
    assert.equal(result.nextDraft.models.mainModel, "saved-model");
    assert.equal(result.bindingsError, "bindings unavailable");
  });
});
