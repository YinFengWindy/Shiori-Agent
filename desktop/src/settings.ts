import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

type SettingsChannelGroup = {
  groupId: string;
  allowFrom: string[];
  requireAt: boolean;
};

type SettingsQQBotGroup = {
  groupOpenid: string;
  allowFrom: string[];
  requireAt: boolean;
  allowProactive: boolean;
};

type SettingsPeerAgent = {
  name: string;
  baseUrl: string;
  launcher: string[];
  cwd: string;
  description: string;
  healthPath: string;
  startupTimeoutSeconds: number;
  shutdownTimeoutSeconds: number;
};

export type SettingsFormData = {
  models: {
    provider: string;
    mainModel: string;
    mainApiKey: string;
    mainBaseUrl: string;
    enableThinking: boolean;
    multimodal: boolean;
    fastModel: string;
    fastApiKey: string;
    fastBaseUrl: string;
    vlModel: string;
    vlApiKey: string;
    vlBaseUrl: string;
  };
  channels: {
    telegramToken: string;
    telegramAllowFrom: string[];
    telegramChannelName: string;
    qqBotUin: string;
    qqAllowFrom: string[];
    qqWebsocketOpenTimeoutSeconds: number;
    qqGroups: SettingsChannelGroup[];
    qqbotAppId: string;
    qqbotClientSecret: string;
    qqbotAllowFrom: string[];
    qqbotGroups: SettingsQQBotGroup[];
    cliSocket: string;
    cliSessionKey: string;
  };
  memory: {
    enabled: boolean;
    engine: string;
    embeddingModel: string;
    embeddingApiKey: string;
    embeddingBaseUrl: string;
    outputDimensionality: string;
  };
  proactive: {
    enabled: boolean;
    profile: string;
    targetChannel: string;
    targetChatId: string;
    agentMaxSteps: number;
    agentContentLimit: number;
    agentWebFetchMaxChars: number;
    agentContextProb: number;
    agentDeliveryCooldownHours: number;
    driftEnabled: boolean;
    driftMaxSteps: number;
    driftMinIntervalHours: number;
  };
  integrations: {
    fitbitEnabled: boolean;
    peerAgents: SettingsPeerAgent[];
  };
  advanced: {
    systemPrompt: string;
    maxTokens: number;
    maxIterations: number;
    devMode: boolean;
    memoryWindow: number;
    searchEnabled: boolean;
    spawnEnabled: boolean;
    memoryOptimizerEnabled: boolean;
    memoryOptimizerIntervalSeconds: number;
    wiringContext: string;
    wiringMemory: string;
    wiringToolsets: string[];
    pluginsRawToml: string;
  };
};

export type SettingsSnapshot = {
  configPath: string;
  formData: SettingsFormData;
};

type SaveSettingsResult = {
  ok: boolean;
  restart: {
    ok: boolean;
    running: boolean;
    lastError: string | null;
  };
  health: {
    ok: boolean;
    message: string;
  };
};

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
    ? value as Record<string, unknown>
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
  let currentArrayName = "";

  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;

    if (line.startsWith("[[") && line.endsWith("]]")) {
      const path = line.slice(2, -2).trim().split(".");
      currentArrayName = path.join(".");
      let cursor: Record<string, unknown> = root;
      for (let index = 0; index < path.length - 1; index += 1) {
        const segment = path[index]!;
        const next = asRecord(cursor[segment]);
        cursor[segment] = next;
        cursor = next;
      }
      const key = path[path.length - 1]!;
      const list = Array.isArray(cursor[key]) ? cursor[key] as Record<string, unknown>[] : [];
      const entry: Record<string, unknown> = {};
      list.push(entry);
      cursor[key] = list;
      current = entry;
      continue;
    }

    if (line.startsWith("[") && line.endsWith("]")) {
      const path = line.slice(1, -1).trim().split(".");
      currentArrayName = "";
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

function loadSettingsData(): SettingsSnapshot {
  const content = existsSync(configPath)
    ? readFileSync(configPath, "utf-8")
    : "";
  const parsed = parseToml(content);
  const llm = asRecord(parsed.llm);
  const llmMain = asRecord(llm.main);
  const llmFast = asRecord(llm.fast);
  const llmVl = asRecord(llm.vl);
  const channels = asRecord(parsed.channels);
  const telegram = asRecord(channels.telegram);
  const qq = asRecord(channels.qq);
  const memory = asRecord(parsed.memory);
  const embedding = asRecord(memory.embedding);
  const proactive = asRecord(parsed.proactive);
  const proactiveTarget = asRecord(proactive.target);
  const proactiveAgent = asRecord(proactive.agent);
  const proactiveDrift = asRecord(proactive.drift);
  const integrations = asRecord(parsed.integrations);
  const fitbit = asRecord(integrations.fitbit);
  const agent = asRecord(parsed.agent);
  const agentContext = asRecord(agent.context);
  const agentTools = asRecord(agent.tools);
  const agentMaintenance = asRecord(agent.maintenance);
  const agentWiring = asRecord(agent.wiring);
  const plugins = asRecord(parsed.plugins);
  const qqbot = asRecord(plugins.qqbot);

  return {
    configPath,
    formData: {
      models: {
        provider: String(llm.provider ?? ""),
        mainModel: String(llmMain.model ?? ""),
        mainApiKey: String(llmMain.api_key ?? ""),
        mainBaseUrl: String(llmMain.base_url ?? ""),
        enableThinking: Boolean(llmMain.enable_thinking),
        multimodal: Boolean(llmMain.multimodal),
        fastModel: String(llmFast.model ?? ""),
        fastApiKey: String(llmFast.api_key ?? ""),
        fastBaseUrl: String(llmFast.base_url ?? ""),
        vlModel: String(llmVl.model ?? ""),
        vlApiKey: String(llmVl.api_key ?? ""),
        vlBaseUrl: String(llmVl.base_url ?? ""),
      },
      channels: {
        telegramToken: String(telegram.token ?? ""),
        telegramAllowFrom: splitList(telegram.allow_from as string[] | undefined),
        telegramChannelName: String(telegram.channel_name ?? "telegram"),
        qqBotUin: String(qq.bot_uin ?? ""),
        qqAllowFrom: splitList(qq.allow_from as string[] | undefined),
        qqWebsocketOpenTimeoutSeconds: Number(qq.websocket_open_timeout_seconds ?? 5),
        qqGroups: asArray(qq.groups, (item) => {
          const group = asRecord(item);
          return {
            groupId: String(group.group_id ?? ""),
            allowFrom: splitList(group.allow_from as string[] | undefined),
            requireAt: Boolean(group.require_at ?? true),
          };
        }),
        qqbotAppId: String(qqbot.app_id ?? ""),
        qqbotClientSecret: String(qqbot.client_secret ?? ""),
        qqbotAllowFrom: splitList(qqbot.allow_from as string[] | undefined),
        qqbotGroups: asArray(qqbot.groups, (item) => {
          const group = asRecord(item);
          return {
            groupOpenid: String(group.group_openid ?? ""),
            allowFrom: splitList(group.allow_from as string[] | undefined),
            requireAt: Boolean(group.require_at ?? true),
            allowProactive: Boolean(group.allow_proactive),
          };
        }),
        cliSocket: String(channels.socket ?? ""),
        cliSessionKey: String(asRecord(channels.cli).session_key ?? ""),
      },
      memory: {
        enabled: Boolean(memory.enabled),
        engine: String(memory.engine ?? ""),
        embeddingModel: String(embedding.model ?? ""),
        embeddingApiKey: String(embedding.api_key ?? ""),
        embeddingBaseUrl: String(embedding.base_url ?? ""),
        outputDimensionality: embedding.output_dimensionality == null ? "" : String(embedding.output_dimensionality),
      },
      proactive: {
        enabled: Boolean(proactive.enabled),
        profile: String(proactive.profile ?? ""),
        targetChannel: String(proactiveTarget.channel ?? ""),
        targetChatId: String(proactiveTarget.chat_id ?? ""),
        agentMaxSteps: Number(proactiveAgent.max_steps ?? 35),
        agentContentLimit: Number(proactiveAgent.content_limit ?? 5),
        agentWebFetchMaxChars: Number(proactiveAgent.web_fetch_max_chars ?? 8000),
        agentContextProb: Number(proactiveAgent.context_prob ?? 0.03),
        agentDeliveryCooldownHours: Number(proactiveAgent.delivery_cooldown_hours ?? 1),
        driftEnabled: Boolean(proactiveDrift.enabled),
        driftMaxSteps: Number(proactiveDrift.max_steps ?? 20),
        driftMinIntervalHours: Number(proactiveDrift.min_interval_hours ?? 3),
      },
      integrations: {
        fitbitEnabled: Boolean(fitbit.enabled),
        peerAgents: asArray(integrations.peer_agents, (item) => {
          const peer = asRecord(item);
          return {
            name: String(peer.name ?? ""),
            baseUrl: String(peer.base_url ?? ""),
            launcher: asArray(peer.launcher, (part) => String(part ?? "")),
            cwd: String(peer.cwd ?? ""),
            description: String(peer.description ?? ""),
            healthPath: String(peer.health_path ?? "/health"),
            startupTimeoutSeconds: Number(peer.startup_timeout_s ?? 30),
            shutdownTimeoutSeconds: Number(peer.shutdown_timeout_s ?? 10),
          };
        }),
      },
      advanced: {
        systemPrompt: String(agent.system_prompt ?? ""),
        maxTokens: Number(agent.max_tokens ?? 8192),
        maxIterations: Number(agent.max_iterations ?? 40),
        devMode: Boolean(agent.dev_mode),
        memoryWindow: Number(agentContext.memory_window ?? 40),
        searchEnabled: Boolean(agentTools.search_enabled),
        spawnEnabled: Boolean(agentTools.spawn_enabled ?? true),
        memoryOptimizerEnabled: Boolean(agentMaintenance.memory_optimizer_enabled ?? true),
        memoryOptimizerIntervalSeconds: Number(agentMaintenance.memory_optimizer_interval_seconds ?? 64800),
        wiringContext: String(agentWiring.context ?? "default"),
        wiringMemory: String(agentWiring.memory ?? "default"),
        wiringToolsets: asArray(agentWiring.toolsets, (item) => String(item ?? "")),
        pluginsRawToml: renderPluginBlocks(
          Object.entries(plugins)
            .filter(([name]) => name !== "qqbot")
            .map(([name, value]) => renderPluginSection(name, asRecord(value)))
            .join("\n"),
        ).trimEnd(),
      },
    },
  };
}

function renderPluginSection(name: string, value: Record<string, unknown>): string {
  const lines = [`[plugins.${name}]`];
  for (const [key, rawValue] of Object.entries(value)) {
    if (Array.isArray(rawValue)) {
      lines.push(`${key} = ${renderStringArray(rawValue.map((item) => String(item ?? "")))}`);
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

function renderSettingsToml(formData: SettingsFormData): string {
  const qqGroupBlocks = formData.channels.qqGroups
    .filter((group) => group.groupId.trim())
    .map((group) => [
      "[[channels.qq.groups]]",
      `group_id = ${quote(group.groupId.trim())}`,
      `allow_from = ${renderStringArray(group.allowFrom)}`,
      `require_at = ${group.requireAt ? "true" : "false"}`,
      "",
    ].join("\n"))
    .join("\n");

  const qqbotGroupBlocks = formData.channels.qqbotGroups
    .filter((group) => group.groupOpenid.trim())
    .map((group) => [
      "[[plugins.qqbot.groups]]",
      `group_openid = ${quote(group.groupOpenid.trim())}`,
      `allow_from = ${renderStringArray(group.allowFrom)}`,
      `require_at = ${group.requireAt ? "true" : "false"}`,
      `allow_proactive = ${group.allowProactive ? "true" : "false"}`,
      "",
    ].join("\n"))
    .join("\n");

  const peerAgentBlocks = formData.integrations.peerAgents
    .filter((agent) => agent.name.trim() || agent.baseUrl.trim())
    .map((agent) => [
      "[[integrations.peer_agents]]",
      `name = ${quote(agent.name.trim())}`,
      `base_url = ${quote(agent.baseUrl.trim())}`,
      `launcher = ${renderStringArray(agent.launcher.filter((part) => part.trim()))}`,
      `cwd = ${quote(agent.cwd.trim())}`,
      `description = ${quote(agent.description)}`,
      `health_path = ${quote(agent.healthPath || "/health")}`,
      `startup_timeout_s = ${agent.startupTimeoutSeconds}`,
      `shutdown_timeout_s = ${agent.shutdownTimeoutSeconds}`,
      "",
    ].join("\n"))
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
    `multimodal = ${formData.models.multimodal ? "true" : "false"}`,
    "",
    "[llm.fast]",
    `model = ${quote(formData.models.fastModel)}`,
    `api_key = ${quote(formData.models.fastApiKey)}`,
    `base_url = ${quote(formData.models.fastBaseUrl)}`,
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
    `memory_optimizer_enabled = ${formData.advanced.memoryOptimizerEnabled ? "true" : "false"}`,
    `memory_optimizer_interval_seconds = ${formData.advanced.memoryOptimizerIntervalSeconds}`,
    "",
    "[agent.wiring]",
    `context = ${quote(formData.advanced.wiringContext)}`,
    `memory = ${quote(formData.advanced.wiringMemory)}`,
    `toolsets = ${renderStringArray(formData.advanced.wiringToolsets)}`,
    "",
    "[channels.telegram]",
    `token = ${quote(formData.channels.telegramToken)}`,
    `allow_from = ${renderStringArray(formData.channels.telegramAllowFrom)}`,
    `channel_name = ${quote(formData.channels.telegramChannelName || "telegram")}`,
    "",
    "[channels.qq]",
    `bot_uin = ${quote(formData.channels.qqBotUin)}`,
    `allow_from = ${renderStringArray(formData.channels.qqAllowFrom)}`,
    `websocket_open_timeout_seconds = ${formData.channels.qqWebsocketOpenTimeoutSeconds}`,
    "",
    qqGroupBlocks,
    "[channels.cli]",
    `socket = ${quote(formData.channels.cliSocket)}`,
    `session_key = ${quote(formData.channels.cliSessionKey)}`,
    "",
    "[plugins.qqbot]",
    `app_id = ${quote(formData.channels.qqbotAppId)}`,
    `client_secret = ${quote(formData.channels.qqbotClientSecret)}`,
    `allow_from = ${renderStringArray(formData.channels.qqbotAllowFrom)}`,
    "",
    qqbotGroupBlocks,
    "[memory]",
    `enabled = ${formData.memory.enabled ? "true" : "false"}`,
    `engine = ${quote(formData.memory.engine)}`,
    "",
    "[memory.embedding]",
    `model = ${quote(formData.memory.embeddingModel)}`,
    `api_key = ${quote(formData.memory.embeddingApiKey)}`,
    `base_url = ${quote(formData.memory.embeddingBaseUrl)}`,
    outputDimensionality ? `output_dimensionality = ${Number(outputDimensionality)}` : "",
    "",
    "[proactive]",
    `enabled = ${formData.proactive.enabled ? "true" : "false"}`,
    `profile = ${quote(formData.proactive.profile)}`,
    "",
    "[proactive.target]",
    `channel = ${quote(formData.proactive.targetChannel)}`,
    `chat_id = ${quote(formData.proactive.targetChatId)}`,
    "",
    "[proactive.agent]",
    `max_steps = ${formData.proactive.agentMaxSteps}`,
    `content_limit = ${formData.proactive.agentContentLimit}`,
    `web_fetch_max_chars = ${formData.proactive.agentWebFetchMaxChars}`,
    `context_prob = ${formData.proactive.agentContextProb}`,
    `delivery_cooldown_hours = ${formData.proactive.agentDeliveryCooldownHours}`,
    "",
    "[proactive.drift]",
    `enabled = ${formData.proactive.driftEnabled ? "true" : "false"}`,
    `max_steps = ${formData.proactive.driftMaxSteps}`,
    `min_interval_hours = ${formData.proactive.driftMinIntervalHours}`,
    "",
    "[integrations.fitbit]",
    `enabled = ${formData.integrations.fitbitEnabled ? "true" : "false"}`,
    "",
    peerAgentBlocks,
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
  if (!formData.channels.telegramChannelName.trim()) {
    throw new Error("Telegram channel name 不能为空");
  }
  if (formData.channels.qqWebsocketOpenTimeoutSeconds <= 0) {
    throw new Error("QQ websocket 超时必须大于 0");
  }
  if (formData.advanced.maxTokens <= 0) {
    throw new Error("max_tokens 必须大于 0");
  }
  if (formData.advanced.maxIterations < 0) {
    throw new Error("max_iterations 不能小于 0");
  }
  if (formData.memory.outputDimensionality.trim()) {
    const value = Number(formData.memory.outputDimensionality);
    if (!Number.isInteger(value) || value <= 0) {
      throw new Error("embedding output_dimensionality 必须是正整数");
    }
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
  const health = restart.ok ? await checkHealth() : {
    ok: false,
    message: restart.lastError || "bridge restart failed",
  };
  return {
    ok: restart.ok && health.ok,
    restart,
    health,
  };
}

export { loadSettingsData };
