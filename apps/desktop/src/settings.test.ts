import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { describe, it } from "node:test";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { configureSettingsConfigPath, loadSettingsData, saveSettings } from "./settings.js";
import { desktopSettingsDefaults } from "./settingsContract.js";

describe("desktop settings config path", () => {
  it("requires the runtime path contract instead of falling back to the repository root", () => {
    assert.throws(() => loadSettingsData(), /桌面配置路径尚未初始化/);
  });

  it("loads settings from the configured workspace path", () => {
    const directory = mkdtempSync(join(tmpdir(), "shiori-settings-"));
    const configPath = join(directory, "workspace", "config.toml");
    try {
      mkdirSync(join(directory, "workspace"), { recursive: true });
      writeFileSync(configPath, "[llm]\n", { encoding: "utf-8" });
      configureSettingsConfigPath(configPath);

      const snapshot = loadSettingsData();

      assert.equal(snapshot.configPath, configPath);
      assert.deepEqual(snapshot.formData.voice, {
        enabled: false,
        hotkey: "Ctrl+Space",
        microphoneDeviceId: "",
        asrEnabled: false,
        asrProvider: desktopSettingsDefaults.asrProvider,
        asrBaseUrl: desktopSettingsDefaults.asrBaseUrl,
        asrSecretId: "",
        asrSecretKey: "",
        ttsEnabled: false,
        ttsProvider: desktopSettingsDefaults.ttsProvider,
        ttsBaseUrl: desktopSettingsDefaults.ttsBaseUrl,
        ttsModel: desktopSettingsDefaults.ttsModel,
        ttsApiKey: "",
        ttsVolume: desktopSettingsDefaults.ttsVolume,
      });
    } finally {
      rmSync(directory, { recursive: true, force: true });
    }
  });

  it("submits a candidate and deferred bindings without overwriting the active file", async () => {
    const directory = mkdtempSync(join(tmpdir(), "shiori-settings-save-"));
    const configPath = join(directory, "workspace", "config.toml");
    try {
      mkdirSync(join(directory, "workspace"), { recursive: true });
      writeFileSync(configPath, "[llm]\n", { encoding: "utf-8" });
      configureSettingsConfigPath(configPath);
      const formData = loadSettingsData().formData;
      formData.models.registrations = [{
        id: "00000000-0000-4000-a000-000000000001",
        provider: "openai",
        baseUrl: "",
        apiKey: "",
        model: "test-model",
        effort: "none",
      }];
      formData.pendingRoleModelUpdates = [{ roleId: "role-1", runtimeConfig: { dialogue_model_registration_id: "" } }];
      let applyCalls = 0;

      const result = await saveSettings(formData, async (request) => {
        applyCalls += 1;
        assert.match(request.config_toml, /model = "test-model"/);
        assert.equal(request.expected_generation, 3);
        assert.equal(request.preserve_plugins, true);
        assert.equal(request.operation_id, "retry-operation");
        assert.deepEqual(request.role_model_updates, [{ role_id: "role-1", runtime_config: { dialogue_model_registration_id: "" } }]);
        return { ok: false, error: { code: "runtime_apply_failed", message: "candidate failed" } };
      }, { expectedGeneration: 3, operationId: "retry-operation" });

      assert.equal(applyCalls, 1);
      assert.equal(result.ok, false);
      assert.equal(readFileSync(configPath, "utf-8"), "[llm]\n");
    } finally {
      rmSync(directory, { recursive: true, force: true });
    }
  });

  it("serializes empty registrations explicitly and accepts incomplete connection details", async () => {
    configureSettingsConfigPath(join(tmpdir(), "unused-config-path.toml"));
    const formData = loadSettingsData("[llm]\nregistrations = []\n").formData;
    await saveSettings(formData, async (request) => {
      assert.match(request.config_toml, /\[llm\]\nregistrations = \[\]/);
      assert.deepEqual(request.role_model_updates, []);
      return { ok: true, generation: 2, changed: true };
    });
    formData.models.registrations = [{ id: "00000000-0000-4000-a000-000000000001", model: "", provider: "openai", apiKey: "", baseUrl: "", effort: "none" }];
    const result = await saveSettings(formData, async () => ({ ok: true, generation: 3 }));
    assert.equal(result.ok, true);
  });
});


describe("core proactive strategy settings round-trip", () => {
  const cases = [
    {
      name: "keeps marker-migrated disabled preferences after an unrelated save",
      source: "[agent.proactive_strategies]\nscene_followup = false\nrelationship = false\n",
      preferences: { sceneFollowup: false, relationship: false },
      expectedLines: ["scene_followup = false", "relationship = false"],
      absentLines: [],
    },
    {
      name: "keeps explicit core enablement above an old disabled plugin preference",
      source: "[plugins.relationship_proactive]\nenabled = false\n[agent.proactive_strategies]\nscene_followup = true\nrelationship = true\n",
      preferences: { sceneFollowup: true, relationship: true },
      expectedLines: ["scene_followup = true", "relationship = true"],
      absentLines: [],
    },
    {
      name: "leaves absent core preferences to backend defaults and marker migration",
      source: "[agent]\nmax_tokens = 4096\n",
      preferences: {},
      expectedLines: [],
      absentLines: ["[agent.proactive_strategies]", "scene_followup =", "relationship ="],
    },
    {
      name: "preserves unmigrated plugin disablement without forcing core defaults",
      source: "[plugins.relationship_proactive]\nenabled = false\n",
      preferences: {},
      expectedLines: [],
      absentLines: ["[agent.proactive_strategies]", "scene_followup =", "relationship ="],
    },
    {
      name: "keeps per-key core precedence and legacy fallback for a missing key",
      source: "[plugins.relationship_proactive]\nenabled = false\n[agent.proactive_strategies]\nscene_followup = true\n",
      preferences: { sceneFollowup: true },
      expectedLines: ["scene_followup = true"],
      absentLines: ["relationship ="],
    },
  ];

  for (const scenario of cases) {
    it(scenario.name, async () => {
      configureSettingsConfigPath(join(tmpdir(), "unused-proactive-settings.toml"));
      const draft = loadSettingsData(scenario.source).formData;
      assert.deepEqual(draft.proactiveStrategies, scenario.preferences);
      draft.advanced.maxTokens += 1;
      let applyCalls = 0;
      const result = await saveSettings(draft, async (request) => {
        applyCalls += 1;
        for (const line of scenario.expectedLines) assert.ok(request.config_toml.includes(line), line);
        for (const line of scenario.absentLines) assert.ok(!request.config_toml.includes(line), line);
        assert.deepEqual(loadSettingsData(request.config_toml).formData.proactiveStrategies, scenario.preferences);
        return { ok: true, generation: 2, changed: true };
      });
      assert.equal(result.ok, true);
      assert.equal(applyCalls, 1);
    });
  }

  it("rejects invalid core switches rather than replacing them with a default", () => {
    configureSettingsConfigPath(join(tmpdir(), "unused-proactive-settings.toml"));
    assert.throws(() => loadSettingsData('[agent.proactive_strategies]\nrelationship = "false"\n'), /必须是布尔值/);
  });
});


describe("settings TOML comments", () => {
  it("round-trips commented booleans and quoted hashes without changing their values", async () => {
    configureSettingsConfigPath(join(tmpdir(), "unused-commented-settings.toml"));
    const source = String.raw`
[agent.proactive_strategies] # core preferences
scene_followup = false # disabled
relationship = true # enabled
[plugins.example]
tags = ["item#one", "item#two"] # tags
path = "C:\\" # escaped slash before closing quote
`;
    const draft = loadSettingsData(source).formData;
    assert.deepEqual(draft.proactiveStrategies, { sceneFollowup: false, relationship: true });
    let applyCalls = 0;
    const result = await saveSettings(draft, async (request) => {
      applyCalls += 1;
      assert.match(request.config_toml, /scene_followup = false/);
      assert.match(request.config_toml, /relationship = true/);
      const saved = loadSettingsData(request.config_toml).formData;
      assert.deepEqual(saved.proactiveStrategies, draft.proactiveStrategies);
      return { ok: true, generation: 2, changed: true };
    });
    assert.equal(result.ok, true);
    assert.equal(applyCalls, 1);
  });

  for (const value of ['"false" # still a string', "'false' # still a literal string"]) {
    it(`rejects a quoted boolean with an inline comment: ${value}`, () => {
      configureSettingsConfigPath(join(tmpdir(), "unused-commented-settings.toml"));
      assert.throws(() => loadSettingsData(`[agent.proactive_strategies]\nrelationship = ${value}\n`), /必须是布尔值/);
    });
  }
});


describe("core scene observation settings", () => {
  it("preserves an explicit core disable over the retired plugin preference", async () => {
    const directory = mkdtempSync(join(tmpdir(), "shiori-scene-settings-"));
    try {
      const path = join(directory, "config.toml");
      writeFileSync(path, "[agent.scene_observation] # core\nenabled = false # disabled\n[plugins.scene_awareness]\nenabled = true\n", "utf-8");
      configureSettingsConfigPath(path);
      const form = loadSettingsData().formData;
      assert.equal(form.advanced.sceneObservationEnabled, false);
      form.advanced.maxTokens += 1;
      await saveSettings(form, async (request) => {
        assert.match(request.config_toml, /\[agent\.scene_observation\]\nenabled = false/);
        return { success: true };
      });
    } finally {
      rmSync(directory, { recursive: true, force: true });
    }
  });
});


for (const legacy of ["", "[plugins.scene_awareness]\nenabled = false\n"]) {
  it("keeps an absent scene core preference available for backend marker migration", async () => {
    const directory = mkdtempSync(join(tmpdir(), "shiori-scene-absent-"));
    try {
      const path = join(directory, "config.toml");
      writeFileSync(path, legacy, "utf-8");
      configureSettingsConfigPath(path);
      const form = loadSettingsData().formData;
      assert.equal(form.advanced.sceneObservationEnabled, undefined);
      await saveSettings(form, async (request) => {
        assert.doesNotMatch(request.config_toml, /\[agent\.scene_observation\]/);
        assert.equal(request.preserve_plugins, true);
        assert.doesNotMatch(request.config_toml, /\[plugins/);
        return { success: true };
      });
    } finally {
      rmSync(directory, { recursive: true, force: true });
    }
  });
}


it("preserves a core scene opt-in over an old plugin disable", async () => {
  const directory = mkdtempSync(join(tmpdir(), "shiori-scene-enabled-"));
  try {
    const path = join(directory, "config.toml");
    writeFileSync(path, "[agent.scene_observation]\nenabled = true\n[plugins.scene_awareness]\nenabled = false\n", "utf-8");
    configureSettingsConfigPath(path);
    const form = loadSettingsData().formData;
    assert.equal(form.advanced.sceneObservationEnabled, true);
    await saveSettings(form, async (request) => {
      assert.match(request.config_toml, /\[agent\.scene_observation\]\nenabled = true/);
      return { success: true };
    });
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

it("reads ordinary settings alongside complex plugin TOML and delegates preservation", async () => {
  const directory = mkdtempSync(join(tmpdir(), "shiori-complex-plugin-settings-"));
  try {
    const path = join(directory, "config.toml");
    writeFileSync(path, `
[agent]
max_tokens = 4096
[plugins.qqbot]
app_id = "app"
client_secret = "secret"
[plugins."unknown.id"]
id = 9223372036854775807
items = [{ name = "a", ports = [1, 2] }]
body = """line one
[looks.like.header]
line three"""
[[plugins."unknown.id".routes]]
name = "route"
[plugins."unknown.id".routes.options]
active = true
`, "utf-8");
    configureSettingsConfigPath(path);
    const form = loadSettingsData().formData;
    assert.equal(form.advanced.maxTokens, 4096);
    assert.ok(!Object.keys(form.advanced).some((key) => key.startsWith("plugins")));
    form.advanced.maxTokens = 8192;
    await saveSettings(form, async (request) => {
      assert.equal(request.preserve_plugins, true);
      assert.doesNotMatch(request.config_toml, /\[plugins/);
      assert.match(request.config_toml, /max_tokens = 8192/);
      return { ok: true, generation: 2, changed: true };
    });
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
});

describe("migrated channel tables", () => {
  it("never writes [channels.telegram|qq] back; the backend rejects a non-empty one (#363)", async () => {
    configureSettingsConfigPath(join(tmpdir(), "unused-migrated-channels.toml"));
    const draft = loadSettingsData('[channels.telegram]\ntoken = "legacy"\n\n[channels.qq]\nbot_uin = "10001"\n').formData;
    let rendered = "";
    await saveSettings(draft, async (request) => {
      rendered = request.config_toml;
      return { ok: true, generation: 2, changed: true };
    });
    assert.doesNotMatch(rendered, /\[channels/);
  });
});
