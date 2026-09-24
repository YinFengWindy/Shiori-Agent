import type { ModelRegistrationFormData } from "../../../src/bridge/shared";

/**
 * A known OpenAI-compatible Chat Completions endpoint. The backend talks to
 * every registration through the OpenAI client, and only reads `provider` to
 * pick a request strategy (DeepSeek / DashScope thinking switches), so a preset
 * is just a provider id plus the base URL that client needs.
 */
export type ModelProviderPreset = {
  id: string;
  label: string;
  provider: string;
  baseUrl: string;
  /** Example model id shown as the model field placeholder. */
  modelHint: string;
};

/** Selection value for a hand-entered provider and base URL. */
export const customProviderPresetId = "custom";

/** Presets offered by the provider select, all verified to speak Chat Completions. */
export const modelProviderPresets: ReadonlyArray<ModelProviderPreset> = [
  { id: "openai", label: "OpenAI", provider: "openai", baseUrl: "https://api.openai.com/v1", modelHint: "gpt-4.1-mini" },
  { id: "deepseek", label: "DeepSeek", provider: "deepseek", baseUrl: "https://api.deepseek.com", modelHint: "deepseek-chat" },
  { id: "dashscope", label: "阿里云百炼", provider: "dashscope", baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1", modelHint: "qwen-plus" },
  { id: "moonshot", label: "月之暗面 Kimi", provider: "moonshot", baseUrl: "https://api.moonshot.cn/v1", modelHint: "kimi-k2-0905-preview" },
  { id: "zhipu", label: "智谱 GLM", provider: "zhipu", baseUrl: "https://open.bigmodel.cn/api/paas/v4", modelHint: "glm-4.5" },
  { id: "siliconflow", label: "硅基流动", provider: "siliconflow", baseUrl: "https://api.siliconflow.cn/v1", modelHint: "Qwen/Qwen3-32B" },
  { id: "openrouter", label: "OpenRouter", provider: "openrouter", baseUrl: "https://openrouter.ai/api/v1", modelHint: "openai/gpt-4.1-mini" },
  { id: "ollama", label: "Ollama（本地）", provider: "ollama", baseUrl: "http://localhost:11434/v1", modelHint: "qwen3:8b" },
];

/** Options for the provider select: every preset, then the custom entry last. */
export const modelProviderOptions: ReadonlyArray<{ value: string; label: string }> = [
  ...modelProviderPresets.map((preset) => ({ value: preset.id, label: preset.label })),
  { value: customProviderPresetId, label: "自定义" },
];

function normalizeBaseUrl(value: string) {
  return value.trim().replace(/\/+$/, "").toLowerCase();
}

/** Finds the preset a registration currently matches exactly, if any. */
export function findProviderPreset(registration: Pick<ModelRegistrationFormData, "provider" | "baseUrl">) {
  const provider = registration.provider.trim().toLowerCase();
  const baseUrl = normalizeBaseUrl(registration.baseUrl);
  return modelProviderPresets.find((preset) => preset.provider === provider && normalizeBaseUrl(preset.baseUrl) === baseUrl);
}

/** Fills provider and base URL from a preset; other fields, including the key, are kept. */
export function applyProviderPreset(registration: ModelRegistrationFormData, presetId: string): ModelRegistrationFormData {
  const preset = modelProviderPresets.find((item) => item.id === presetId);
  if (!preset) return registration;
  return { ...registration, provider: preset.provider, baseUrl: preset.baseUrl };
}
