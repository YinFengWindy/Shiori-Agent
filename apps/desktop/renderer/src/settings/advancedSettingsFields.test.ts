import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { advancedSettingsGroups } from "./advancedSettingsFields";
import { createSettingsDraft } from "./testFixtures";

describe("advancedSettingsGroups", () => {
  const fields = advancedSettingsGroups.flatMap((group) => group.fields);

  it("maps every advanced setting except the moved display preference to a Chinese label over its config key", () => {
    const covered = new Set<string>(fields.map((field) => field.key));
    const expected = Object.keys(createSettingsDraft().advanced).filter((key) => key !== "streamingEnabled");
    assert.deepEqual([...covered].sort(), expected.sort());
    assert.equal(covered.has("streamingEnabled"), false, "实时显示回复 lives in 设置 › 外观");
    for (const field of fields) {
      assert.match(field.label, /[\u4e00-\u9fff]/, `${field.key} needs a Chinese label`);
      assert.match(field.configKey, /^[a-z_]+$/, `${field.key} keeps its raw config key`);
    }
  });

  it("uses each config key once and gives numeric rows their unit", () => {
    assert.equal(new Set(fields.map((field) => field.configKey)).size, fields.length);
    const units = Object.fromEntries(fields.filter((field) => field.kind === "number").map((field) => [field.configKey, field.unit]));
    assert.deepEqual(units, {
      max_tokens: "token",
      max_iterations: "步",
      memory_window: "条",
      memory_optimizer_interval_seconds: "秒",
      consolidation_input_token_threshold: "token",
    });
    assert.deepEqual(advancedSettingsGroups.map((group) => group.title), ["对话", "能力", "记忆整理", "开发者"]);
  });
});
