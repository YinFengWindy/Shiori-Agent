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

  it("saves without restarting the bridge", async () => {
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
      let healthChecks = 0;

      const result = await saveSettings(formData, async () => {
        healthChecks += 1;
        return { ok: true, message: "ok" };
      });

      assert.equal(healthChecks, 1);
      assert.equal(result.ok, true);
      assert.match(readFileSync(configPath, "utf-8"), /model = "test-model"/);
    } finally {
      rmSync(directory, { recursive: true, force: true });
    }
  });
});
