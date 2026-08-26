import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { describe, it } from "node:test";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { configureSettingsConfigPath, loadSettingsData } from "./settings.js";
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
});
