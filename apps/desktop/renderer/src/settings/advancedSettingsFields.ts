import type { SettingsFormData } from "../shared/types";

type AdvancedSettings = SettingsFormData["advanced"];
type NumberKey = { [K in keyof AdvancedSettings]-?: AdvancedSettings[K] extends number ? K : never }[keyof AdvancedSettings];
type ToggleKey = { [K in keyof AdvancedSettings]-?: AdvancedSettings[K] extends boolean | undefined ? K : never }[keyof AdvancedSettings];

/** One row of 设置 › 高级: a Chinese label over the raw config.toml key it edits. */
export type AdvancedSettingsField =
  | { kind: "number"; key: NumberKey; configKey: string; label: string; unit?: string }
  | { kind: "toggle"; key: ToggleKey; configKey: string; label: string };

/** A titled group of advanced rows. */
export type AdvancedSettingsGroup = { title: string; fields: AdvancedSettingsField[] };

/**
 * The advanced page's layout, as data so the label ↔ key mapping is tested
 * in one place. `streaming_enabled` is deliberately absent: it is an
 * everyday display preference and lives in 设置 › 外观.
 */
export const advancedSettingsGroups: readonly AdvancedSettingsGroup[] = [
  {
    title: "对话",
    fields: [
      { kind: "number", key: "maxTokens", configKey: "max_tokens", label: "单次回复长度上限", unit: "token" },
      { kind: "number", key: "maxIterations", configKey: "max_iterations", label: "单次任务最多步数", unit: "步" },
      { kind: "number", key: "memoryWindow", configKey: "memory_window", label: "上下文保留消息数", unit: "条" },
    ],
  },
  {
    title: "能力",
    fields: [
      { kind: "toggle", key: "searchEnabled", configKey: "search_enabled", label: "联网搜索" },
      { kind: "toggle", key: "spawnEnabled", configKey: "spawn_enabled", label: "创建子任务" },
    ],
  },
  {
    title: "记忆整理",
    fields: [
      { kind: "toggle", key: "memoryOptimizerEnabled", configKey: "memory_optimizer_enabled", label: "后台整理记忆" },
      { kind: "number", key: "memoryOptimizerIntervalSeconds", configKey: "memory_optimizer_interval_seconds", label: "整理间隔", unit: "秒" },
      { kind: "number", key: "consolidationInputTokenThreshold", configKey: "consolidation_input_token_threshold", label: "会话历史整理阈值", unit: "token" },
    ],
  },
  {
    title: "开发者",
    fields: [
      { kind: "toggle", key: "devMode", configKey: "dev_mode", label: "开发者模式" },
    ],
  },
];
