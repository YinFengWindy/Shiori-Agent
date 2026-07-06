/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { createDefaultRoleMoodConfig, readRoleMoodConfig, roleMoodConfigEqual, writeRoleMoodConfigToRuntimeConfig } from "./roleMoodConfig";

describe("roleMoodConfig", () => {
  it("builds a stable default mood config", () => {
    assert.deepEqual(createDefaultRoleMoodConfig(), {
      moodCatalog: ["平静"],
      defaultMood: "平静",
      moodIllustrationBindings: {},
    });
  });

  it("normalizes mood config from runtime config", () => {
    const config = readRoleMoodConfig({
      runtime_config: {
        default_mood: "开心",
        mood_catalog: ["开心", "平静", "开心", ""],
        mood_illustration_bindings: {
          开心: "happy.png",
          平静: "calm.png",
          警觉: "alert.png",
        },
      },
    });

    assert.deepEqual(config, {
      moodCatalog: ["开心", "平静"],
      defaultMood: "开心",
      moodIllustrationBindings: {
        开心: "happy.png",
        平静: "calm.png",
      },
    });
  });

  it("derives mood catalog from bound illustrations when no manual catalog should be shown", () => {
    const config = readRoleMoodConfig({
      runtime_config: {
        default_mood: "不存在",
        mood_catalog: ["平静", "开心", "生气"],
        mood_illustration_bindings: {
          开心: "happy.png",
          平静: "calm.png",
        },
      },
    });

    assert.deepEqual(config, {
      moodCatalog: ["开心", "平静"],
      defaultMood: "开心",
      moodIllustrationBindings: {
        开心: "happy.png",
        平静: "calm.png",
      },
    });
  });

  it("writes mood config back into runtime config while preserving unrelated keys", () => {
    const runtimeConfig = writeRoleMoodConfigToRuntimeConfig(
      { nsfw_memory_enabled: true },
      {
        moodCatalog: ["警觉", "平静"],
        defaultMood: "警觉",
        moodIllustrationBindings: {
          警觉: "alert.png",
          平静: "calm.png",
          空白: "",
        },
      },
    );

    assert.deepEqual(runtimeConfig, {
      nsfw_memory_enabled: true,
      default_mood: "警觉",
      mood_catalog: ["警觉", "平静"],
      mood_illustration_bindings: {
        警觉: "alert.png",
        平静: "calm.png",
      },
    });
  });

  it("writes default mood from the first bound illustration when the requested default is no longer bound", () => {
    const runtimeConfig = writeRoleMoodConfigToRuntimeConfig(
      { nsfw_memory_enabled: true },
      {
        moodCatalog: ["平静", "开心"],
        defaultMood: "无奈",
        moodIllustrationBindings: {
          开心: "happy.png",
          平静: "calm.png",
        },
      },
    );

    assert.deepEqual(runtimeConfig, {
      nsfw_memory_enabled: true,
      default_mood: "开心",
      mood_catalog: ["开心", "平静"],
      mood_illustration_bindings: {
        开心: "happy.png",
        平静: "calm.png",
      },
    });
  });

  it("compares mood config by normalized values", () => {
    assert.equal(
      roleMoodConfigEqual(
        {
          moodCatalog: ["平静", "开心"],
          defaultMood: "平静",
          moodIllustrationBindings: { 开心: "happy.png" },
        },
        {
          moodCatalog: ["平静", "开心"],
          defaultMood: "平静",
          moodIllustrationBindings: { 开心: "happy.png" },
        },
      ),
      true,
    );
  });
});
