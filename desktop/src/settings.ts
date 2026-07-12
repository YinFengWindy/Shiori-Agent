import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

import type {
  SaveSettingsResult,
  SettingsBindingsSnapshot,
  SettingsChannelGroup,
  SettingsChannelRoleBinding,
  SettingsFormData,
  SettingsSnapshot,
} from "./shared.js";

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

function splitList(value: string | string[] | undefined): string[] {
  if (Array.isArray(value)) {
    return value
      .map((item) => String(item).trim())
      .filter(Boolean);
  }
  if (!value) return [];
  return String(value)
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asArray<T>(value: unknown, mapper: (item: unknown) => T): T[] {
  return Array.isArray(value) ? value.map(mapper) : [];
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

function sanitizeChannelRoleBindings(
  bindings: SettingsChannelRoleBinding[],
): SettingsChannelRoleBinding[] {
  return bindings
    .map((binding) => ({
      channel: String(binding.channel ?? "").trim(),
      chatId: String(binding.chatId ?? "").trim(),
      roleId: String(binding.roleId ?? "").trim(),
    }))
    .filter((binding) => binding.channel && binding.chatId && binding.roleId);
}

export function loadSettingsData(): SettingsSnapshot {
  const content = existsSync(configPath) ? readFileSync(configPath, "utf-8") : "";
  const parsed = parseToml(content);
  const llm = asRecord(parsed.llm);
  const llmMain = asRecord(llm.main);
  const llmFast = asRecord(llm.fast);
  const llmAgent = asRecord(llm.agent);
  const llmVl = asRecord(llm.vl);
  const channels = asRecord(parsed.channels);
  const telegram = asRecord(channels.telegram);
  const qq = asRecord(channels.qq);
  const memory = asRecord(parsed.memory);
  const embedding = asRecord(memory.embedding);
  const proactive = asRecord(parsed.proactive);
  const proactiveAgent = asRecord(proactive.agent);
  const proactiveDrift = asRecord(proactive.drift);
  const integrations = asRecord(parsed.integrations);
  const novelai = asRecord(integrations.novelai);
  const agent = asRecord(parsed.agent);
  const agentContext = asRecord(agent.context);
  const agentTools = asRecord(agent.tools);
  const agentMaintenance = asRecord(agent.maintenance);
  const agentEmoji = asRecord(agent.emoji);
  const plugins = asRecord(parsed.plugins);
  return {
    configPath,
    formData: {
      models: {
        provider: String(llm.provider ?? ""),
        mainModel: String(llmMain.model ?? ""),
        mainApiKey: String(llmMain.api_key ?? ""),
        mainBaseUrl: String(llmMain.base_url ?? ""),
        enableThinking: Boolean(llmMain.enable_thinking),
        reasoningEffort: String(llmMain.reasoning_effort ?? ""),
        multimodal: Boolean(llmMain.multimodal),
        fastModel: String(llmFast.model ?? ""),
        fastApiKey: String(llmFast.api_key ?? ""),
        fastBaseUrl: String(llmFast.base_url ?? ""),
        agentModel: String(llmAgent.model ?? ""),
        agentApiKey: String(llmAgent.api_key ?? ""),
        agentBaseUrl: String(llmAgent.base_url ?? ""),
        vlModel: String(llmVl.model ?? ""),
        vlApiKey: String(llmVl.api_key ?? ""),
        vlBaseUrl: String(llmVl.base_url ?? ""),
      },
      channels: {
        telegramToken: String(telegram.token ?? ""),
        telegramAllowFrom: splitList(
          telegram.allow_from as string[] | undefined,
        ),
        qqBotUin: String(qq.bot_uin ?? ""),
        qqAllowFrom: splitList(qq.allow_from as string[] | undefined),
        qqGroups: asArray(qq.groups, (item) => {
          const group = asRecord(item);
          return {
            groupId: String(group.group_id ?? ""),
            allowFrom: splitList(group.allow_from as string[] | undefined),
            requireAt: Boolean(group.require_at ?? true),
          } satisfies SettingsChannelGroup;
        }),
        roleBindings: [],
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
      proactive: {
        enabled: Boolean(proactive.enabled),
        profile: String(proactive.profile ?? ""),
        agentMaxSteps: Number(proactiveAgent.max_steps ?? 35),
        agentContentLimit: Number(proactiveAgent.content_limit ?? 5),
        agentWebFetchMaxChars: Number(
          proactiveAgent.web_fetch_max_chars ?? 8000,
        ),
        driftEnabled: Boolean(proactiveDrift.enabled),
        driftMaxSteps: Number(proactiveDrift.max_steps ?? 20),
        driftMinIntervalHours: Number(proactiveDrift.min_interval_hours ?? 3),
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
      emoji: {
        entries: asArray(agentEmoji.entries, (item) => {
          const [name, ...valueParts] = String(item ?? "").split("=");
          return {
            name: name?.trim() ?? "",
            value: valueParts.join("=").trim(),
          };
        }).filter((item) => item.name && item.value),
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
  const qqGroupBlocks = formData.channels.qqGroups
    .filter((group) => group.groupId.trim())
    .map((group) =>
      [
        "[[channels.qq.groups]]",
        `group_id = ${quote(group.groupId.trim())}`,
        `allow_from = ${renderStringArray(group.allowFrom)}`,
        `require_at = ${group.requireAt ? "true" : "false"}`,
        "",
      ].join("\n"),
    )
    .join("\n");

  const outputDimensionality = formData.memory.outputDimensionality.trim();

  return [
    "[llm]",
    `provider = ${quote(formData.models.provider)}`,
    "",
    "[llm.main]",
    `model = ${quote(formData.models.mainModel)}`,
    `api_key = ${quote(formData.models.mainApiKey)}`,
    `base_url = ${quote(formData.models.mainBaseUrl)}`,
    `enable_thinking = ${formData.models.enableThinking ? "true" : "false"}`,
    formData.models.reasoningEffort.trim()
      ? `reasoning_effort = ${quote(formData.models.reasoningEffort.trim())}`
      : "",
    `multimodal = ${formData.models.multimodal ? "true" : "false"}`,
    "",
    "[llm.fast]",
    `model = ${quote(formData.models.fastModel)}`,
    `api_key = ${quote(formData.models.fastApiKey)}`,
    `base_url = ${quote(formData.models.fastBaseUrl)}`,
    "",
    "[llm.agent]",
    `model = ${quote(formData.models.agentModel)}`,
    `api_key = ${quote(formData.models.agentApiKey)}`,
    `base_url = ${quote(formData.models.agentBaseUrl)}`,
    "",
    "[llm.vl]",
    `model = ${quote(formData.models.vlModel)}`,
    `api_key = ${quote(formData.models.vlApiKey)}`,
    `base_url = ${quote(formData.models.vlBaseUrl)}`,
    "",
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
    "[agent.emoji]",
    `entries = ${renderStringArray(
      formData.emoji.entries.map((entry) => `${entry.name.trim()}=${entry.value.trim()}`),
    )}`,
    "",
    "[agent.wiring]",
    'context = "default"',
    'memory = "default"',
    "toolsets = []",
    "",
    "[channels.telegram]",
    `token = ${quote(formData.channels.telegramToken)}`,
    `allow_from = ${renderStringArray(formData.channels.telegramAllowFrom)}`,
    'channel_name = "telegram"',
    "",
    "[channels.qq]",
    `bot_uin = ${quote(formData.channels.qqBotUin)}`,
    `allow_from = ${renderStringArray(formData.channels.qqAllowFrom)}`,
    "websocket_open_timeout_seconds = 5",
    "",
    qqGroupBlocks,
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
    "[proactive]",
    `enabled = ${formData.proactive.enabled ? "true" : "false"}`,
    `profile = ${quote(formData.proactive.profile)}`,
    "",
    "[proactive.agent]",
    `max_steps = ${formData.proactive.agentMaxSteps}`,
    `content_limit = ${formData.proactive.agentContentLimit}`,
    `web_fetch_max_chars = ${formData.proactive.agentWebFetchMaxChars}`,
    "",
    "[proactive.drift]",
    `enabled = ${formData.proactive.driftEnabled ? "true" : "false"}`,
    `max_steps = ${formData.proactive.driftMaxSteps}`,
    `min_interval_hours = ${formData.proactive.driftMinIntervalHours}`,
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
  if (!formData.models.mainModel.trim()) {
    throw new Error("主模型不能为空");
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
  const emojiNames = formData.emoji.entries.map((entry) => entry.name.trim().toLowerCase());
  for (let index = 0; index < formData.emoji.entries.length; index += 1) {
    const entry = formData.emoji.entries[index]!;
    if (!/^[a-z0-9_-]+$/i.test(entry.name.trim())) {
      throw new Error("Emoji 名称只能包含字母、数字、下划线和连字符");
    }
    if (!entry.value.trim()) {
      throw new Error("Emoji 字符不能为空");
    }
  }
  if (emojiNames.length !== new Set(emojiNames).size) {
    throw new Error("Emoji 名称不能重复");
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

export function loadChannelRoleBindings(
  bindings: SettingsChannelRoleBinding[],
): SettingsBindingsSnapshot {
  return {
    bindings: sanitizeChannelRoleBindings(bindings),
  };
}
