import type { SettingsSectionId } from "./SettingsSidebar";
import type { RoleRecord, SettingsFormData } from "../shared/types";

export type SettingsSubsection = {
  id: string;
  label: string;
};

export type SettingsStatusTone = "neutral" | "success" | "warning";

export type SettingsSectionStatus = {
  label: string;
  tone?: SettingsStatusTone;
};

export type SettingsSectionIntroMeta = {
  title: string;
  summary: string;
  statuses: SettingsSectionStatus[];
};

export const settingsSubsections: Record<SettingsSectionId, SettingsSubsection[]> = {
  models: [
    { id: "main", label: "主模型" },
    { id: "fast", label: "轻量 / 视觉" },
  ],
  channels: [
    { id: "telegram", label: "Telegram" },
    { id: "qq", label: "QQ" },
    { id: "qqbot", label: "QQBot" },
    { id: "feishu", label: "Feishu" },
    { id: "cli", label: "CLI" },
  ],
  memory: [
    { id: "general", label: "基础" },
    { id: "embedding", label: "Embedding" },
  ],
  proactive: [
    { id: "general", label: "开关与目标" },
    { id: "agent", label: "推送行为" },
    { id: "drift", label: "Drift" },
  ],
  integrations: [
    { id: "novelai", label: "NovelAI" },
    { id: "fitbit", label: "Fitbit" },
    { id: "peer-agents", label: "Peer Agents" },
  ],
  advanced: [
    { id: "general", label: "基础" },
    { id: "wiring", label: "Wiring" },
    { id: "plugins", label: "插件 / TOML" },
  ],
};

function configuredStatus(configured: boolean, configuredLabel = "已配置", emptyLabel = "未配置"): SettingsSectionStatus {
  return {
    label: configured ? configuredLabel : emptyLabel,
    tone: configured ? "success" : "warning",
  };
}

/** Builds the current subsection title, summary, and status badges for the settings header. */
export function buildSettingsSectionIntro(
  section: SettingsSectionId,
  subsectionId: string,
  draft: SettingsFormData,
  roles: RoleRecord[],
  dirty: boolean,
): SettingsSectionIntroMeta {
  const dirtyStatus = dirty ? [{ label: "有未保存修改", tone: "warning" as const }] : [];

  switch (section) {
    case "models":
      if (subsectionId === "fast") {
        return {
          title: "更多模型通道",
          summary: "把轻量、Agent、视觉模型放到同一层管理，按实际运行路径分别覆盖。",
          statuses: [
            configuredStatus(Boolean(draft.models.fastModel.trim()), "已配置轻量模型", "轻量模型未配置"),
            configuredStatus(Boolean(draft.models.agentModel.trim()), "已配置 Agent 模型", "Agent 模型未配置"),
            configuredStatus(Boolean(draft.models.vlModel.trim()), "已配置视觉模型", "视觉模型未配置"),
            ...dirtyStatus,
          ],
        };
      }
      return {
        title: "主模型",
        summary: "配置桌面主对话的主入口，并决定 Thinking、多模态和推理强度的默认行为。",
        statuses: [
          configuredStatus(Boolean(draft.models.mainApiKey.trim()), "已配置 API Key", "主模型 API Key 未配置"),
          {
            label: draft.models.mainBaseUrl.trim() ? "自定义 Base URL" : "使用默认地址",
            tone: draft.models.mainBaseUrl.trim() ? "neutral" : "success",
          },
          {
            label: draft.models.enableThinking ? "Thinking 已启用" : "Thinking 未启用",
            tone: draft.models.enableThinking ? "success" : "neutral",
          },
          ...dirtyStatus,
        ],
      };
    case "channels":
      return {
        title: settingsSubsections.channels.find((item) => item.id === subsectionId)?.label ?? "频道",
        summary: "按 transport 维护接入凭据、允许范围和角色绑定，不需要的频道可以保持留空。",
        statuses: [
          {
            label: draft.channels.roleBindings.some((binding) => binding.channel === subsectionId) ? "已有角色绑定" : "暂无角色绑定",
            tone: draft.channels.roleBindings.some((binding) => binding.channel === subsectionId) ? "success" : "neutral",
          },
          ...dirtyStatus,
        ],
      };
    case "memory":
      return {
        title: subsectionId === "embedding" ? "Embedding" : "记忆",
        summary: subsectionId === "embedding"
          ? "覆盖向量化模型、地址和输出维度；不填时继续走现有默认行为。"
          : "控制记忆总开关和所使用的引擎，不改这里就沿用当前默认 wiring。",
        statuses: [
          {
            label: draft.memory.enabled ? "记忆已启用" : "记忆未启用",
            tone: draft.memory.enabled ? "success" : "warning",
          },
          {
            label: draft.memory.engine.trim() ? `引擎：${draft.memory.engine}` : "使用默认引擎",
            tone: draft.memory.engine.trim() ? "neutral" : "success",
          },
          ...dirtyStatus,
        ],
      };
    case "proactive":
      if (subsectionId === "agent") {
        return {
          title: "推送行为",
          summary: "控制主动推送的运行画像、冷却时间和 Agent 限制；只在主动推送启用后生效。",
          statuses: [
            {
              label: draft.proactive.enabled ? "主动推送已启用" : "仅启用后生效",
              tone: draft.proactive.enabled ? "success" : "warning",
            },
            {
              label: draft.proactive.profile.trim() ? `配置档：${draft.proactive.profile}` : "未指定配置档",
              tone: draft.proactive.profile.trim() ? "neutral" : "warning",
            },
            ...dirtyStatus,
          ],
        };
      }
      if (subsectionId === "drift") {
        return {
          title: "Drift",
          summary: "Drift 是附加策略层，不替代普通主动推送主流程，用于低频探索性外推。",
          statuses: [
            {
              label: draft.proactive.driftEnabled ? "Drift 已启用" : "Drift 未启用",
              tone: draft.proactive.driftEnabled ? "success" : "neutral",
            },
            {
              label: draft.proactive.enabled ? "依赖主动推送主开关" : "仅启用主开关后生效",
              tone: draft.proactive.enabled ? "neutral" : "warning",
            },
            ...dirtyStatus,
          ],
        };
      }
      return {
        title: "开关与目标",
        summary: "先决定是否启用主动推送，再指定目标频道、默认角色和实际投递目标。",
        statuses: [
          {
            label: draft.proactive.enabled ? "主动推送已启用" : "主动推送未启用",
            tone: draft.proactive.enabled ? "success" : "warning",
          },
          {
            label: draft.proactive.targetRoleId.trim()
              ? `目标角色：${roles.find((role) => role.id === draft.proactive.targetRoleId)?.name ?? draft.proactive.targetRoleId}`
              : "目标角色未配置",
            tone: draft.proactive.targetRoleId.trim() ? "success" : "warning",
          },
          {
            label: draft.proactive.targetChannel.trim() ? `目标频道：${draft.proactive.targetChannel}` : "目标频道未配置",
            tone: draft.proactive.targetChannel.trim() ? "neutral" : "warning",
          },
          ...dirtyStatus,
        ],
      };
    case "integrations":
      if (subsectionId === "fitbit") {
        return {
          title: "Fitbit",
          summary: "这里仅保留启用状态和作用说明，没有启用时不会接入任何 Fitbit 相关路径。",
          statuses: [
            {
              label: draft.integrations.fitbitEnabled ? "Fitbit 已启用" : "Fitbit 未启用",
              tone: draft.integrations.fitbitEnabled ? "success" : "neutral",
            },
            ...dirtyStatus,
          ],
        };
      }
      if (subsectionId === "peer-agents") {
        return {
          title: "Peer Agents",
          summary: "注册外部 Agent 节点；列表为空时不会向运行时注册任何外部代理。",
          statuses: [
            {
              label: draft.integrations.peerAgents.length ? `已登记 ${draft.integrations.peerAgents.length} 个` : "未登记外部 Agent",
              tone: draft.integrations.peerAgents.length ? "success" : "neutral",
            },
            ...dirtyStatus,
          ],
        };
      }
      return {
        title: "NovelAI",
        summary: "把接入凭据、默认生成行为和权限限制拆开管理，未启用时整组参数都不会生效。",
        statuses: [
          {
            label: draft.integrations.novelaiEnabled ? "NovelAI 已启用" : "NovelAI 未启用",
            tone: draft.integrations.novelaiEnabled ? "success" : "warning",
          },
          configuredStatus(Boolean(draft.integrations.novelaiToken.trim()), "已配置 Token", "Token 未配置"),
          {
            label: draft.integrations.novelaiBaseUrl.trim() ? "自定义 Base URL" : "使用默认地址",
            tone: draft.integrations.novelaiBaseUrl.trim() ? "neutral" : "success",
          },
          ...dirtyStatus,
        ],
      };
    case "advanced":
      return {
        title: settingsSubsections.advanced.find((item) => item.id === subsectionId)?.label ?? "高级",
        summary: "保留不适合频繁改动的运行参数和原始 TOML 入口，常用配置优先放在前面分组处理。",
        statuses: [
          {
            label: subsectionId === "plugins" ? "原始 TOML 区" : "高级运行参数",
            tone: "neutral",
          },
          ...dirtyStatus,
        ],
      };
    default:
      return {
        title: "设置",
        summary: "当前分组暂无摘要。",
        statuses: dirtyStatus,
      };
  }
}
