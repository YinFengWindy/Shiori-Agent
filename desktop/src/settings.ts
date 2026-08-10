import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

import type {
  ModelRegistrationFormData,
  SaveSettingsResult,
  SettingsFormData,
  SettingsSnapshot,
} from "./shared.js";
import { parseHotkey } from "./voice/hotkey.js";

type BridgeRestarter = () => Promise<{
  ok: boolean;
  running: boolean;
  lastError: string | null;
}>;

type BridgeHealthChecker = () => Promise<{
  ok: boolean;
  message: string;
}>;

const configPath = resolve(import.meta.dirname, "..", "..", "config.toml");

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function parseTomlValue(raw: string): unknown {
  const value = raw.trim();
  if (value.startsWith("\"") && value.endsWith("\"")) {
    return JSON.parse(value);
  }
  if (value === "true") return true;
  if (value === "false") return false;
  if (/^-?\d+(\.\d+)?$/.test(value)) return Number(value);
  if (value.startsWith("[") && value.endsWith("]")) {
    return JSON.parse(value);
  }
  return value;
}

function parseToml(content: string): Record<string, unknown> {
  const root: Record<string, unknown> = {};
  let current = root;

  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;

    if (line.startsWith("[[") && line.endsWith("]]")) {
      const path = line.slice(2, -2).trim().split(".");
      let cursor: Record<string, unknown> = root;
      for (let index = 0; index < path.length - 1; index += 1) {
        const segment = path[index]!;
        const next = asRecord(cursor[segment]);
        cursor[segment] = next;
        cursor = next;
      }
      const key = path[path.length - 1]!;
      const list = Array.isArray(cursor[key])
        ? (cursor[key] as Record<string, unknown>[])
        : [];
      const entry: Record<string, unknown> = {};
      list.push(entry);
      cursor[key] = list;
      current = entry;
      continue;
    }

    if (line.startsWith("[") && line.endsWith("]")) {
      const path = line.slice(1, -1).trim().split(".");
      let cursor: Record<string, unknown> = root;
      for (const segment of path) {
        const next = asRecord(cursor[segment]);
        cursor[segment] = next;
        cursor = next;
      }
      current = cursor;
      continue;
    }

    const separatorIndex = line.indexOf("=");
    if (separatorIndex < 0) continue;
    const key = line.slice(0, separatorIndex).trim();
    const rawValue = line.slice(separatorIndex + 1).trim();
    current[key] = parseTomlValue(rawValue);
  }

  return root;
}

function quote(value: string): string {
  return JSON.stringify(value ?? "");
}

function renderStringArray(values: string[]): string {
  return `[${values.map((item) => quote(item)).join(", ")}]`;
}

function renderPluginBlocks(rawToml: string): string {
  const trimmed = rawToml.trim();
  return trimmed ? `${trimmed}\n` : "";
}

function renderPluginSection(name: string, value: Record<string, unknown>): string {
  const lines = [`[plugins.${name}]`];
  for (const [key, rawValue] of Object.entries(value)) {
    if (Array.isArray(rawValue)) {
      lines.push(
        `${key} = ${renderStringArray(rawValue.map((item) => String(item ?? "")))}`,
      );
      continue;
    }
    if (typeof rawValue === "boolean") {
      lines.push(`${key} = ${rawValue ? "true" : "false"}`);
      continue;
    }
    if (typeof rawValue === "number") {
      lines.push(`${key} = ${rawValue}`);
      continue;
    }
    lines.push(`${key} = ${quote(String(rawValue ?? ""))}`);
  }
  return lines.join("\n");
}

function loadModelRegistrations(llm: Record<string, unknown>): ModelRegistrationFormData[] {
  const raw = Array.isArray(llm.registrations) ? llm.registrations : [];
  return raw.map((value) => {
    const item = asRecord(value);
    return {
      id: String(item.id ?? ""),
      provider: String(item.provider ?? "openai"),
      baseUrl: String(item.base_url ?? ""),
      apiKey: String(item.api_key ?? ""),
      model: String(item.model ?? ""),
      effort: String(item.effort ?? "none") as "none" | "low" | "high" | "max",
    };
  });
}

export function loadSettingsData(): SettingsSnapshot {
  const content = existsSync(configPath) ? readFileSync(configPath, "utf-8") : "";
  const parsed = parseToml(content);
  const llm = asRecord(parsed.llm);
  const channels = asRecord(parsed.channels);
  const telegram = asRecord(channels.telegram);
  const qq = asRecord(channels.qq);
  const memory = asRecord(parsed.memory);
  const embedding = asRecord(memory.embedding);
  const integrations = asRecord(parsed.integrations);
  const novelai = asRecord(integrations.novelai);
  const agent = asRecord(parsed.agent);
  const agentContext = asRecord(agent.context);
  const agentTools = asRecord(agent.tools);
  const agentMaintenance = asRecord(agent.maintenance);
  const voice = asRecord(parsed.voice);
  const voiceAsr = asRecord(voice.asr);
  const voiceTts = asRecord(voice.tts);
  const plugins = asRecord(parsed.plugins);
  const qqbot = asRecord(plugins.qqbot);
  return {
    configPath,
    formData: {
      models: {
        registrations: loadModelRegistrations(llm),
      },
      channels: {
        telegramToken: String(telegram.token ?? ""),
        qqBotUin: String(qq.bot_uin ?? ""),
        qqBotAppId: String(qqbot.app_id ?? qqbot.appId ?? ""),
        qqBotClientSecret: String(qqbot.client_secret ?? qqbot.clientSecret ?? ""),
      },
      memory: {
        enabled: Boolean(memory.enabled),
        engine: String(memory.engine ?? ""),
        embeddingModel: String(embedding.model ?? ""),
        embeddingApiKey: String(embedding.api_key ?? ""),
        embeddingBaseUrl: String(embedding.base_url ?? ""),
        outputDimensionality:
          embedding.output_dimensionality == null
            ? ""
            : String(embedding.output_dimensionality),
      },
      integrations: {
        novelaiEnabled: Boolean(novelai.enabled),
        novelaiToken: String(novelai.token ?? ""),
        novelaiNsfwEnabled: Boolean(novelai.nsfw_enabled),
        novelaiAddQualityTags: Boolean(novelai.add_quality_tags),
        novelaiUndesiredContentPreset: Number(
          novelai.undesired_content_preset ?? 0,
        ),
        novelaiAutoWritebackRoleAssets: Boolean(
          novelai.auto_writeback_role_assets,
        ),
      },
      voice: {
        enabled: Boolean(voice.enabled),
        hotkey: String(voice.hotkey ?? "Ctrl+Space"),
        microphoneDeviceId: String(voice.microphone_device_id ?? ""),
        asrEnabled: Boolean(voiceAsr.enabled ?? voice.enabled),
        asrProvider: String(voiceAsr.provider ?? "tencent"),
        asrBaseUrl: String(voiceAsr.base_url ?? "https://asr.tencentcloudapi.com/"),
        asrSecretId: String(voiceAsr.secret_id ?? ""),
        asrSecretKey: String(voiceAsr.secret_key ?? ""),
        ttsEnabled: Boolean(voiceTts.enabled ?? voice.enabled),
        ttsProvider: String(voiceTts.provider ?? "minimax"),
        ttsBaseUrl: String(voiceTts.base_url ?? "https://api.minimaxi.com/v1/t2a_v2"),
        ttsModel: String(voiceTts.model ?? "speech-2.8-turbo"),
        ttsApiKey: String(voiceTts.api_key ?? ""),
        ttsVolume: Number(voiceTts.volume ?? 2.0),
      },
      advanced: {
        systemPrompt: String(agent.system_prompt ?? ""),
        maxTokens: Number(agent.max_tokens ?? 8192),
        maxIterations: Number(agent.max_iterations ?? 40),
        devMode: Boolean(agent.dev_mode),
        memoryWindow: Number(agentContext.memory_window ?? 40),
        searchEnabled: Boolean(agentTools.search_enabled),
        spawnEnabled: Boolean(agentTools.spawn_enabled ?? true),
        memoryOptimizerEnabled: Boolean(
          agentMaintenance.memory_optimizer_enabled ?? true,
        ),
        memoryOptimizerIntervalSeconds: Number(
          agentMaintenance.memory_optimizer_interval_seconds ?? 64800,
        ),
        pluginsRawToml: renderPluginBlocks(
          Object.entries(plugins)
            .filter(([name]) => name !== "qqbot" && name !== "feishu")
            .map(([name, value]) => renderPluginSection(name, asRecord(value)))
            .join("\n"),
        ).trimEnd(),
      },
    },
  };
}

function renderSettingsToml(formData: SettingsFormData): string {
  const outputDimensionality = formData.memory.outputDimensionality.trim();

  return [
    "[llm]",
    "",
    ...formData.models.registrations.flatMap((registration) => [
      "[[llm.registrations]]",
      `id = ${quote(registration.id)}`,
      `provider = ${quote(registration.provider.trim())}`,
      `base_url = ${quote(registration.baseUrl.trim())}`,
      `api_key = ${quote(registration.apiKey)}`,
      `model = ${quote(registration.model.trim())}`,
      `effort = ${quote(registration.effort)}`,
      "",
    ]),
    "[agent]",
    `system_prompt = ${quote(formData.advanced.systemPrompt)}`,
    `max_tokens = ${formData.advanced.maxTokens}`,
    `max_iterations = ${formData.advanced.maxIterations}`,
    `dev_mode = ${formData.advanced.devMode ? "true" : "false"}`,
    "",
    "[agent.context]",
    `memory_window = ${formData.advanced.memoryWindow}`,
    "",
    "[agent.tools]",
    `search_enabled = ${formData.advanced.searchEnabled ? "true" : "false"}`,
    `spawn_enabled = ${formData.advanced.spawnEnabled ? "true" : "false"}`,
    "",
    "[agent.maintenance]",
    `memory_optimizer_enabled = ${
      formData.advanced.memoryOptimizerEnabled ? "true" : "false"
    }`,
    `memory_optimizer_interval_seconds = ${formData.advanced.memoryOptimizerIntervalSeconds}`,
    "",
    "[agent.wiring]",
    'context = "default"',
    'memory = "default"',
    "toolsets = []",
    "",
    "[channels.telegram]",
    `token = ${quote(formData.channels.telegramToken)}`,
    'channel_name = "telegram"',
    "",
    "[channels.qq]",
    `bot_uin = ${quote(formData.channels.qqBotUin)}`,
    "websocket_open_timeout_seconds = 5",
    "",
    "[plugins.qqbot]",
    `app_id = ${quote(formData.channels.qqBotAppId)}`,
    `client_secret = ${quote(formData.channels.qqBotClientSecret)}`,
    "",
    "[memory]",
    `enabled = ${formData.memory.enabled ? "true" : "false"}`,
    `engine = ${quote(formData.memory.engine)}`,
    "",
    "[memory.embedding]",
    `model = ${quote(formData.memory.embeddingModel)}`,
    `api_key = ${quote(formData.memory.embeddingApiKey)}`,
    `base_url = ${quote(formData.memory.embeddingBaseUrl)}`,
    outputDimensionality
      ? `output_dimensionality = ${Number(outputDimensionality)}`
      : "",
    "",
    "[integrations.novelai]",
    `enabled = ${formData.integrations.novelaiEnabled ? "true" : "false"}`,
    `token = ${quote(formData.integrations.novelaiToken)}`,
    'base_url = "https://image.novelai.net"',
    'default_model = "nai-diffusion-4-5-curated"',
    'nsfw_model = "nai-diffusion-4-5-full"',
    `nsfw_enabled = ${
      formData.integrations.novelaiNsfwEnabled ? "true" : "false"
    }`,
    `add_quality_tags = ${
      formData.integrations.novelaiAddQualityTags ? "true" : "false"
    }`,
    `undesired_content_preset = ${formData.integrations.novelaiUndesiredContentPreset}`,
    "allow_txt2img = true",
    "allow_img2img = true",
    `auto_writeback_role_assets = ${
      formData.integrations.novelaiAutoWritebackRoleAssets ? "true" : "false"
    }`,
    "max_pixels = 1048576",
    "max_steps = 28",
    "default_samples = 1",
    "",
    "[voice]",
    `enabled = ${formData.voice.enabled ? "true" : "false"}`,
    `hotkey = ${quote(formData.voice.hotkey.trim())}`,
    `microphone_device_id = ${quote(formData.voice.microphoneDeviceId.trim())}`,
    "",
    "[voice.asr]",
    `provider = ${quote(formData.voice.asrProvider.trim())}`,
    `base_url = ${quote(formData.voice.asrBaseUrl.trim())}`,
    `enabled = ${(formData.voice.asrEnabled ?? formData.voice.enabled) ? "true" : "false"}`,
    `secret_id = ${quote(formData.voice.asrSecretId)}`,
    `secret_key = ${quote(formData.voice.asrSecretKey)}`,
    "",
    "[voice.tts]",
    `provider = ${quote(formData.voice.ttsProvider.trim())}`,
    `base_url = ${quote(formData.voice.ttsBaseUrl.trim())}`,
    `model = ${quote(formData.voice.ttsModel.trim())}`,
    `enabled = ${(formData.voice.ttsEnabled ?? formData.voice.enabled) ? "true" : "false"}`,
    `api_key = ${quote(formData.voice.ttsApiKey)}`,
    `volume = ${formData.voice.ttsVolume}`,
    "",
    formData.advanced.pluginsRawToml.trim(),
    "",
  ]
    .filter((line, index, array) => {
      if (line !== "") return true;
      return index > 0 && array[index - 1] !== "";
    })
    .join("\n")
    .trim()
    .concat("\n");
}

function validateSettings(formData: SettingsFormData): void {
  if (formData.models.registrations.length === 0) {
    throw new Error("至少需要一个模型注册");
  }
  const registrationIds = new Set<string>();
  for (const registration of formData.models.registrations) {
    if (!registration.id || !registration.model.trim()) {
      throw new Error("模型注册 ID 和模型不能为空");
    }
    if (registrationIds.has(registration.id)) {
      throw new Error("模型注册 ID 不能重复");
    }
    if (!["none", "low", "high", "max"].includes(registration.effort)) {
      throw new Error("Effort 必须是 none、low、high 或 max");
    }
    registrationIds.add(registration.id);
  }
  if (formData.advanced.maxTokens <= 0) {
    throw new Error("max_tokens 必须大于 0");
  }
  if (formData.advanced.maxIterations < 0) {
    throw new Error("max_iterations 不能小于 0");
  }
  if (
    !Number.isInteger(formData.integrations.novelaiUndesiredContentPreset) ||
    formData.integrations.novelaiUndesiredContentPreset < 0
  ) {
    throw new Error("NovelAI undesired content preset 必须是非负整数");
  }
  if (formData.memory.outputDimensionality.trim()) {
    const value = Number(formData.memory.outputDimensionality);
    if (!Number.isInteger(value) || value <= 0) {
      throw new Error("embedding output_dimensionality 必须是正整数");
    }
  }
  if (formData.voice.enabled && !parseHotkey(formData.voice.hotkey)) {
    throw new Error("语音快捷键格式无效");
  }
  if (!["tencent"].includes(formData.voice.asrProvider.trim())) {
    throw new Error("ASR Provider 不受支持");
  }
  if (!["minimax"].includes(formData.voice.ttsProvider.trim())) {
    throw new Error("TTS Provider 不受支持");
  }
  if (!Number.isFinite(formData.voice.ttsVolume) || formData.voice.ttsVolume < 0.1 || formData.voice.ttsVolume > 10) {
    throw new Error("TTS 音量必须在 0.1 到 10.0 之间");
  }
}

export async function saveSettings(
  formData: SettingsFormData,
  restartBridge: BridgeRestarter,
  checkHealth: BridgeHealthChecker,
): Promise<SaveSettingsResult> {
  validateSettings(formData);
  writeFileSync(configPath, renderSettingsToml(formData), { encoding: "utf-8" });
  const restart = await restartBridge();
  const health = restart.ok
    ? await checkHealth()
    : {
        ok: false,
        message: restart.lastError || "bridge restart failed",
      };
  return {
    ok: restart.ok && health.ok,
    restart,
    health,
  };
}
