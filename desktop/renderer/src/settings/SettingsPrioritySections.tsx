import type React from "react";
import { cx, ghostButtonClass, inputClass } from "../shared/styles";
import { PeerAgentEditor } from "./SettingsEditors";
import { formatLauncher, parseLauncher } from "./settingsFormHelpers";
import { parseNumber } from "./settingsFormHelpers";
import {
  ReadOnlySettingInput,
  SecretInput,
  SettingsCard,
  SettingsExpandableBlock,
  SettingsField,
  SettingsFieldHint,
} from "./settingsUi";
import type { SettingsSectionContentProps } from "./settingsSectionTypes";

const proactiveTargetOptions = [
  { value: "desktop", label: "桌面端" },
  { value: "telegram", label: "Telegram" },
  { value: "qq", label: "QQ" },
  { value: "qqbot", label: "QQBot" },
  { value: "feishu", label: "Feishu" },
  { value: "cli", label: "CLI" },
];

function fieldStatus(configured: boolean, configuredLabel = "已配置", emptyLabel = "未配置") {
  return configured
    ? { label: configuredLabel, tone: "success" as const }
    : { label: emptyLabel, tone: "warning" as const };
}

/** Renders the high-frequency settings sections: models, proactive, and integrations. */
export function renderPrioritySettingsSection({
  section,
  subsectionId,
  draft,
  roles,
  updateDraft,
  updateProactiveTargetChannel,
  updateProactiveTargetRoleId,
}: SettingsSectionContentProps): React.ReactNode {
  const desktopTargetRoleId = draft.proactive.targetRoleId.trim();
  const desktopTargetChatId = desktopTargetRoleId ? `role:${desktopTargetRoleId}` : "";

  if (section === "models") {
    if (subsectionId === "fast") {
      return (
        <div className="grid gap-6">
          <SettingsCard title="轻量模型" summary="给轻量路径单独指定模型和凭据；不填则继续沿用默认回退行为。">
            <SettingsField label="轻量模型" description="用于轻量推理路径，不需要时可以保留空白。" badge={fieldStatus(Boolean(draft.models.fastModel.trim()), "已配置轻量模型", "轻量模型未配置")} hint={<SettingsFieldHint usage="覆盖轻量模型通道的模型名。" blank="留空时继续走默认模型回退路径。" effect="影响轻量推理、成本更敏感或速度优先的运行路径。" configPath="models.fast_model" />}>
              <input className={cx(inputClass, "bg-white")} value={draft.models.fastModel} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, fastModel: event.target.value } }))} placeholder="例如 gpt-4.1-mini" />
            </SettingsField>
            <SettingsField label="轻量模型 API Key" description="只在轻量模型通道单独鉴权时需要填写。" badge={fieldStatus(Boolean(draft.models.fastApiKey.trim()), "已配置 Key", "沿用默认 Key")} hint={<SettingsFieldHint usage="覆盖轻量模型通道的鉴权凭据。" blank="留空时继续沿用默认 API Key。" effect="只影响轻量模型相关请求。" configPath="models.fast_api_key" />}>
              <SecretInput value={draft.models.fastApiKey} onChange={(value) => updateDraft((current) => ({ ...current, models: { ...current.models, fastApiKey: value } }))} />
            </SettingsField>
            <SettingsField label="轻量模型 Base URL" description="需要走独立网关或代理时再填写。" badge={{ label: draft.models.fastBaseUrl.trim() ? "自定义地址" : "使用默认地址", tone: draft.models.fastBaseUrl.trim() ? "neutral" : "success" }} hint={<SettingsFieldHint usage="覆盖轻量模型通道的服务地址。" blank="留空时使用 provider 默认地址。" effect="影响轻量模型请求入口。" configPath="models.fast_base_url" />}>
              <input className={cx(inputClass, "bg-white")} value={draft.models.fastBaseUrl} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, fastBaseUrl: event.target.value } }))} placeholder="https://api.example.com/v1" />
            </SettingsField>
          </SettingsCard>
          <SettingsCard title="Agent 模型" summary="供主动推送和 agent tick 等独立通道使用，不配置时仍可走默认模型。">
            <SettingsField label="Agent 模型" description="只在希望让主动推送 / Agent 通道单独走另一套模型时填写。" badge={fieldStatus(Boolean(draft.models.agentModel.trim()), "已配置 Agent 模型", "Agent 模型未配置")} hint={<SettingsFieldHint usage="覆盖主动推送和 Agent 相关路径的模型名。" blank="留空时继续使用默认模型回退路径。" effect="影响主动推送与 agent tick 侧的请求。" configPath="models.agent_model" />}>
              <input className={cx(inputClass, "bg-white")} value={draft.models.agentModel} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, agentModel: event.target.value } }))} placeholder="例如 gpt-4.1" />
            </SettingsField>
            <SettingsExpandableBlock>
              <SettingsField label="Agent API Key" description="仅在 Agent 通道需要独立鉴权时填写。" badge={fieldStatus(Boolean(draft.models.agentApiKey.trim()), "已配置 Key", "沿用默认 Key")} hint={<SettingsFieldHint usage="覆盖 Agent 通道的鉴权凭据。" blank="留空时沿用默认 API Key。" effect="只影响 Agent 相关请求。" configPath="models.agent_api_key" />}>
                <SecretInput value={draft.models.agentApiKey} onChange={(value) => updateDraft((current) => ({ ...current, models: { ...current.models, agentApiKey: value } }))} />
              </SettingsField>
              <SettingsField label="Agent Base URL" description="为 Agent 通道指定独立入口。" badge={{ label: draft.models.agentBaseUrl.trim() ? "自定义地址" : "使用默认地址", tone: draft.models.agentBaseUrl.trim() ? "neutral" : "success" }} hint={<SettingsFieldHint usage="覆盖 Agent 通道的服务地址。" blank="留空时使用 provider 默认地址。" effect="影响 Agent 相关请求入口。" configPath="models.agent_base_url" />}>
                <input className={cx(inputClass, "bg-white")} value={draft.models.agentBaseUrl} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, agentBaseUrl: event.target.value } }))} placeholder="https://api.example.com/v1" />
              </SettingsField>
            </SettingsExpandableBlock>
          </SettingsCard>
          <SettingsCard title="视觉模型" summary="给图像理解或多模态识图路径使用，不配置时继续走默认视觉能力。">
            <SettingsField label="视觉模型" description="用于视觉识别或独立 VL 路径，不需要时可留空。" badge={fieldStatus(Boolean(draft.models.vlModel.trim()), "已配置视觉模型", "视觉模型未配置")} hint={<SettingsFieldHint usage="覆盖视觉模型通道的模型名。" blank="留空时继续使用默认视觉模型回退路径。" effect="影响图像理解和视觉能力入口。" configPath="models.vl_model" />}>
              <input className={cx(inputClass, "bg-white")} value={draft.models.vlModel} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, vlModel: event.target.value } }))} placeholder="例如 gpt-4.1-mini" />
            </SettingsField>
            <SettingsExpandableBlock>
              <SettingsField label="视觉模型 API Key" description="仅在视觉通道需要单独凭据时填写。" badge={fieldStatus(Boolean(draft.models.vlApiKey.trim()), "已配置 Key", "沿用默认 Key")} hint={<SettingsFieldHint usage="覆盖视觉模型通道的鉴权凭据。" blank="留空时沿用默认 API Key。" effect="只影响视觉模型请求。" configPath="models.vl_api_key" />}>
                <SecretInput value={draft.models.vlApiKey} onChange={(value) => updateDraft((current) => ({ ...current, models: { ...current.models, vlApiKey: value } }))} />
              </SettingsField>
              <SettingsField label="视觉模型 Base URL" description="需要把视觉请求单独导向别的网关时再填写。" badge={{ label: draft.models.vlBaseUrl.trim() ? "自定义地址" : "使用默认地址", tone: draft.models.vlBaseUrl.trim() ? "neutral" : "success" }} hint={<SettingsFieldHint usage="覆盖视觉模型通道的服务地址。" blank="留空时使用 provider 默认地址。" effect="影响视觉模型请求入口。" configPath="models.vl_base_url" />}>
                <input className={cx(inputClass, "bg-white")} value={draft.models.vlBaseUrl} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, vlBaseUrl: event.target.value } }))} placeholder="https://api.example.com/v1" />
              </SettingsField>
            </SettingsExpandableBlock>
          </SettingsCard>
        </div>
      );
    }

    return (
      <div className="grid gap-6">
        <SettingsCard title="主模型连接" summary="优先配置主模型入口，留空的覆盖项会继续沿用 provider 默认行为。">
          <SettingsField label="Provider" description="当前主模型使用的提供商标识。" badge={draft.models.provider.trim() ? { label: draft.models.provider, tone: "neutral" } : { label: "未配置", tone: "warning" }} hint={<SettingsFieldHint usage="决定默认请求走哪类模型服务。" blank="保存前应填写有效 provider。" effect="影响主对话与未覆盖的模型请求。" configPath="models.provider" />}>
            <input className={cx(inputClass, "bg-white")} value={draft.models.provider} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, provider: event.target.value } }))} />
          </SettingsField>
          <SettingsField label="主模型" description="桌面主对话使用的模型名。" badge={fieldStatus(Boolean(draft.models.mainModel.trim()), "已配置主模型", "主模型未配置")} hint={<SettingsFieldHint usage="指定桌面主对话默认使用的模型名。" blank="保存前应填写有效模型名。" effect="影响主对话与未单独覆盖的聊天请求。" configPath="models.main_model" />}>
            <input className={cx(inputClass, "bg-white")} value={draft.models.mainModel} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, mainModel: event.target.value } }))} />
          </SettingsField>
          <SettingsField label="主模型 API Key" description="主模型默认鉴权凭据。" badge={fieldStatus(Boolean(draft.models.mainApiKey.trim()), "已配置 API Key", "API Key 未配置")} hint={<SettingsFieldHint usage="为主模型请求提供默认鉴权凭据。" blank="留空时依赖 provider 或运行环境中的默认凭据。" effect="影响主对话与沿用默认 key 的模型通道。" configPath="models.main_api_key" />}>
            <SecretInput value={draft.models.mainApiKey} onChange={(value) => updateDraft((current) => ({ ...current, models: { ...current.models, mainApiKey: value } }))} />
          </SettingsField>
          <SettingsField label="主模型 Base URL" description="覆盖默认模型服务地址。" badge={{ label: draft.models.mainBaseUrl.trim() ? "自定义地址" : "使用默认地址", tone: draft.models.mainBaseUrl.trim() ? "neutral" : "success" }} hint={<SettingsFieldHint usage="覆盖默认模型服务地址。" blank="留空时使用 provider 默认地址。" effect="影响主对话与依赖该模型通道的请求入口。" configPath="models.main_base_url" />}>
            <input className={cx(inputClass, "bg-white")} value={draft.models.mainBaseUrl} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, mainBaseUrl: event.target.value } }))} placeholder="https://api.example.com/v1" />
          </SettingsField>
        </SettingsCard>
        <SettingsCard title="对话能力" summary="集中管理 Thinking、推理强度和多模态开关，让主对话的默认能力一眼可见。">
          <SettingsField label="Thinking" description="打开后允许主模型走带 Thinking 的回复路径。" badge={{ label: draft.models.enableThinking ? "已启用" : "未启用", tone: draft.models.enableThinking ? "success" : "neutral" }} hint={<SettingsFieldHint usage="控制主对话是否启用 Thinking。" blank="不开启时沿用普通对话模式。" effect="影响主对话的回复路径与成本。" configPath="models.enable_thinking" />}>
            <label className="flex items-center gap-3 rounded-[16px] border border-[#E6E9EE] bg-[#FBFBFC] px-4 py-3"><input type="checkbox" checked={draft.models.enableThinking} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, enableThinking: event.target.checked } }))} /><span>启用 Thinking</span></label>
          </SettingsField>
          <SettingsField label="Reasoning Effort" description="支持的模型可用，用于控制推理强度。" badge={{ label: draft.models.reasoningEffort.trim() ? "已指定强度" : "由模型决定", tone: draft.models.reasoningEffort.trim() ? "neutral" : "success" }} hint={<SettingsFieldHint usage="指定模型的推理强度，如 low / medium / high。" blank="留空时不写入配置，由模型或 provider 自行决定。" effect="影响支持 reasoning effort 的模型行为。" recommendation="没有明确调优需求时，先留空。" configPath="models.reasoning_effort" />}>
            <input className={cx(inputClass, "bg-white")} value={draft.models.reasoningEffort} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, reasoningEffort: event.target.value } }))} placeholder="例如 low / medium / high" />
          </SettingsField>
          <SettingsField label="Multimodal" description="控制主对话是否允许多模态能力。" badge={{ label: draft.models.multimodal ? "已启用" : "未启用", tone: draft.models.multimodal ? "success" : "neutral" }} hint={<SettingsFieldHint usage="决定主对话是否允许图片等多模态输入。" blank="关闭时只走文本对话能力。" effect="影响主对话可用的输入能力。" configPath="models.multimodal" />}>
            <label className="flex items-center gap-3 rounded-[16px] border border-[#E6E9EE] bg-[#FBFBFC] px-4 py-3"><input type="checkbox" checked={draft.models.multimodal} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, multimodal: event.target.checked } }))} /><span>启用多模态</span></label>
          </SettingsField>
        </SettingsCard>
      </div>
    );
  }

  if (section === "proactive") {
    if (subsectionId === "agent") {
      return (
        <div className="grid gap-6">
          <SettingsCard title="推送行为" summary="先决定策略配置档和投递冷却，避免主动推送过于频繁。">
            <SettingsField label="配置档" description="主动推送运行时启用的 profile 名称。" badge={{ label: draft.proactive.profile.trim() ? "已指定配置档" : "未指定配置档", tone: draft.proactive.profile.trim() ? "success" : "warning" }} hint={<SettingsFieldHint usage="指定主动推送的运行配置档。" blank="留空时走当前默认配置档解析路径。" effect="影响主动推送行为策略。" configPath="proactive.profile" />}>
              <input className={cx(inputClass, "bg-white")} value={draft.proactive.profile} onChange={(event) => updateDraft((current) => ({ ...current, proactive: { ...current.proactive, profile: event.target.value } }))} />
            </SettingsField>
            <SettingsField label="发送冷却小时数" description="限制同一目标被再次主动投递的最短间隔。" badge={{ label: draft.proactive.enabled ? "启用后生效" : "仅启用后生效", tone: draft.proactive.enabled ? "neutral" : "warning" }} hint={<SettingsFieldHint usage="限制主动推送的最小投递间隔。" blank="未填写时继续使用当前数值。" effect="影响同一目标多久可以再次收到主动消息。" configPath="proactive.agent_delivery_cooldown_hours" />}>
              <input className={cx(inputClass, "bg-white")} value={String(draft.proactive.agentDeliveryCooldownHours)} onChange={(event) => updateDraft((current) => ({ ...current, proactive: { ...current.proactive, agentDeliveryCooldownHours: parseNumber(event.target.value, current.proactive.agentDeliveryCooldownHours) } }))} />
            </SettingsField>
          </SettingsCard>
          <SettingsCard title="Agent 限制" summary="收紧步骤数、内容长度和网页抓取规模，避免主动推送失控。">
            <SettingsField label="最大步数" description="限制 Agent 单次主动推送最多能跑多少步。" hint={<SettingsFieldHint usage="限制主动推送单次运行的最大步骤数。" effect="影响 Agent 的探索深度和耗时。" configPath="proactive.agent_max_steps" />}><input className={cx(inputClass, "bg-white")} value={String(draft.proactive.agentMaxSteps)} onChange={(event) => updateDraft((current) => ({ ...current, proactive: { ...current.proactive, agentMaxSteps: parseNumber(event.target.value, current.proactive.agentMaxSteps) } }))} /></SettingsField>
            <SettingsField label="内容长度限制" description="控制单次主动推送最多生成多少正文。" hint={<SettingsFieldHint usage="限制主动消息正文长度。" effect="影响主动消息最终发送体量。" configPath="proactive.agent_content_limit" />}><input className={cx(inputClass, "bg-white")} value={String(draft.proactive.agentContentLimit)} onChange={(event) => updateDraft((current) => ({ ...current, proactive: { ...current.proactive, agentContentLimit: parseNumber(event.target.value, current.proactive.agentContentLimit) } }))} /></SettingsField>
            <SettingsField label="网页抓取最大字符数" description="限制 web fetch 导入的网页文本规模。" hint={<SettingsFieldHint usage="限制网页抓取后带回上下文的字符数。" effect="影响主动推送访问网页后的上下文体积。" configPath="proactive.agent_web_fetch_max_chars" />}><input className={cx(inputClass, "bg-white")} value={String(draft.proactive.agentWebFetchMaxChars)} onChange={(event) => updateDraft((current) => ({ ...current, proactive: { ...current.proactive, agentWebFetchMaxChars: parseNumber(event.target.value, current.proactive.agentWebFetchMaxChars) } }))} /></SettingsField>
            <SettingsField label="上下文概率" description="控制主动推送采样或引入上下文的概率阈值。" hint={<SettingsFieldHint usage="决定主动推送采样上下文的概率。" effect="影响主动推送的上下文使用密度。" configPath="proactive.agent_context_prob" />}><input className={cx(inputClass, "bg-white")} value={String(draft.proactive.agentContextProb)} onChange={(event) => updateDraft((current) => ({ ...current, proactive: { ...current.proactive, agentContextProb: parseNumber(event.target.value, current.proactive.agentContextProb) } }))} /></SettingsField>
          </SettingsCard>
        </div>
      );
    }
    if (subsectionId === "drift") {
      return (
        <div className="grid gap-6">
          <SettingsCard title="Drift 策略" summary="Drift 作为附加策略使用，不替代普通主动推送主流程。">
            <SettingsField label="启用 Drift" description="控制是否开启 Drift 附加策略。" badge={{ label: draft.proactive.driftEnabled ? "已启用" : "未启用", tone: draft.proactive.driftEnabled ? "success" : "neutral" }} hint={<SettingsFieldHint usage="开启 Drift 附加策略。" blank="关闭时不运行 Drift。" effect="只影响 Drift 路径。" configPath="proactive.drift.enabled" />}><label className="flex items-center gap-3 rounded-[16px] border border-[#E6E9EE] bg-[#FBFBFC] px-4 py-3"><input type="checkbox" checked={draft.proactive.driftEnabled} onChange={(event) => updateDraft((current) => ({ ...current, proactive: { ...current.proactive, driftEnabled: event.target.checked } }))} /><span>proactive.drift.enabled</span></label></SettingsField>
            <SettingsField label="Drift 最大步数" description="限制 Drift 一次最多运行多少步。" hint={<SettingsFieldHint usage="限制 Drift 单次探索的最大步数。" effect="影响 Drift 计算深度和耗时。" configPath="proactive.drift.max_steps" />}><input className={cx(inputClass, "bg-white")} value={String(draft.proactive.driftMaxSteps)} onChange={(event) => updateDraft((current) => ({ ...current, proactive: { ...current.proactive, driftMaxSteps: parseNumber(event.target.value, current.proactive.driftMaxSteps) } }))} /></SettingsField>
            <SettingsField label="Drift 最小间隔小时数" description="限制 Drift 两次运行的最短间隔。" hint={<SettingsFieldHint usage="限制 Drift 最短运行间隔。" effect="影响 Drift 触发频率。" configPath="proactive.drift.min_interval_hours" />}><input className={cx(inputClass, "bg-white")} value={String(draft.proactive.driftMinIntervalHours)} onChange={(event) => updateDraft((current) => ({ ...current, proactive: { ...current.proactive, driftMinIntervalHours: parseNumber(event.target.value, current.proactive.driftMinIntervalHours) } }))} /></SettingsField>
          </SettingsCard>
        </div>
      );
    }
    return (
      <div className="grid gap-6">
        <SettingsCard title="开关与目标" summary="先决定是否启用主动推送，再把投递目标和角色前提配置完整。">
          <SettingsField label="启用主动推送" description="主开关关闭时，该组其他参数都不会生效。" badge={{ label: draft.proactive.enabled ? "已启用" : "未启用", tone: draft.proactive.enabled ? "success" : "warning" }} hint={<SettingsFieldHint usage="决定是否启用主动推送能力。" blank="关闭时其余 proactive 参数不会生效。" effect="影响整个主动推送主流程。" configPath="proactive.enabled" />}><label className="flex items-center gap-3 rounded-[16px] border border-[#E6E9EE] bg-[#FBFBFC] px-4 py-3"><input type="checkbox" checked={draft.proactive.enabled} onChange={(event) => updateDraft((current) => ({ ...current, proactive: { ...current.proactive, enabled: event.target.checked } }))} /><span>proactive.enabled</span></label></SettingsField>
          <SettingsField label="目标频道" description="指定主动消息要投递到哪个 transport。" badge={{ label: draft.proactive.targetChannel.trim() ? draft.proactive.targetChannel : "未选择", tone: draft.proactive.targetChannel.trim() ? "neutral" : "warning" }} hint={<SettingsFieldHint usage="指定主动消息要发送到的频道。" blank="未选择时无法组成有效投递目标。" effect="影响主动消息最终发往哪个 transport。" configPath="proactive.target_channel" />}><select className={cx(inputClass, "bg-white")} value={draft.proactive.targetChannel} onChange={(event) => updateProactiveTargetChannel(event.target.value)}><option value="">请选择目标</option>{proactiveTargetOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></SettingsField>
          <SettingsField label="目标角色" description="启用主动推送的必要前提；桌面端投递也会由该角色派生会话。" badge={{ label: draft.proactive.targetRoleId.trim() ? "已选择角色" : "角色未配置", tone: draft.proactive.targetRoleId.trim() ? "success" : "warning" }} hint={<SettingsFieldHint usage="指定主动推送默认使用的角色。" blank="留空时无法形成完整的主动推送目标。" effect="影响主动推送时使用哪个角色上下文。" configPath="proactive.target_role_id" />}><select className={cx(inputClass, "bg-white")} value={draft.proactive.targetRoleId} onChange={(event) => updateProactiveTargetRoleId(event.target.value)}><option value="" disabled={draft.proactive.enabled}>请选择角色</option>{roles.map((role) => <option key={role.id} value={role.id}>{role.name}</option>)}</select></SettingsField>
          {draft.proactive.targetChannel ? <SettingsField label="Target Chat ID" description="根据频道类型填写实际投递目标；桌面端会自动从角色推导会话。" badge={{ label: draft.proactive.targetChannel === "desktop" ? "自动派生" : "手动填写", tone: draft.proactive.targetChannel === "desktop" ? "success" : "neutral" }} hint={<SettingsFieldHint usage="为选中的目标频道填写实际 chat_id / open_id / session key。" blank={draft.proactive.targetChannel === "desktop" ? "桌面端会自动派生 role:<role_id>。" : "留空时目标频道无法形成完整投递地址。"} effect="影响主动消息真正发到哪里。" configPath="proactive.target_chat_id" />}>{draft.proactive.targetChannel === "desktop" ? <ReadOnlySettingInput value={desktopTargetChatId} placeholder="自动使用 role:<role_id>" /> : <input className={cx(inputClass, "bg-white")} value={draft.proactive.targetChatId} onChange={(event) => updateDraft((current) => ({ ...current, proactive: { ...current.proactive, targetChatId: event.target.value } }))} placeholder="输入 transport chat_id" />}</SettingsField> : null}
        </SettingsCard>
      </div>
    );
  }

  if (section === "integrations") {
    if (subsectionId === "fitbit") {
      return <div className="grid gap-6"><SettingsCard title="Fitbit 接入" summary="当前仅管理启用状态；未启用时不会接入任何 Fitbit 运行路径。"><SettingsField label="启用 Fitbit" description="开启后才会启用 Fitbit 相关能力。" badge={{ label: draft.integrations.fitbitEnabled ? "已启用" : "未启用", tone: draft.integrations.fitbitEnabled ? "success" : "neutral" }} hint={<SettingsFieldHint usage="控制 Fitbit 集成总开关。" blank="关闭时不会启用 Fitbit 能力。" effect="影响 Fitbit 相关运行路径。" configPath="integrations.fitbit.enabled" />}><label className="flex items-center gap-3 rounded-[16px] border border-[#E6E9EE] bg-[#FBFBFC] px-4 py-3"><input type="checkbox" checked={draft.integrations.fitbitEnabled} onChange={(event) => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, fitbitEnabled: event.target.checked } }))} /><span>integrations.fitbit.enabled</span></label></SettingsField></SettingsCard></div>;
    }
    if (subsectionId === "peer-agents") {
      return <div className="grid gap-6"><SettingsCard title="外部 Agent 注册列表" summary="按条目登记外部 Agent；列表为空时不会注册任何外部代理。"><SettingsField label="Peer Agents" description="维护可选的外部 Agent 节点。" badge={draft.integrations.peerAgents.length ? { label: `已登记 ${draft.integrations.peerAgents.length} 个`, tone: "success" } : { label: "列表为空", tone: "neutral" }} hint={<SettingsFieldHint usage="登记可被运行时发现和调用的外部 Agent。" blank="列表为空时不会注册外部代理。" effect="影响运行时可发现的 peer agents。" configPath="integrations.peer_agents" />}><div className="grid gap-3">{draft.integrations.peerAgents.map((agent, index) => <PeerAgentEditor key={`${agent.name}-${index}`} agent={agent} parseNumber={parseNumber} parseLauncher={parseLauncher} formatLauncher={formatLauncher} onChange={(nextAgent) => updateDraft((current) => { const next = [...current.integrations.peerAgents]; next[index] = nextAgent; return { ...current, integrations: { ...current.integrations, peerAgents: next } }; })} onRemove={() => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, peerAgents: current.integrations.peerAgents.filter((_, agentIndex) => agentIndex !== index) } }))} />)}<button className={cx("w-fit rounded-md px-4 py-2 text-sm", ghostButtonClass)} type="button" onClick={() => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, peerAgents: [...current.integrations.peerAgents, { name: "", baseUrl: "", launcher: [], cwd: "", description: "", healthPath: "/health", startupTimeoutSeconds: 30, shutdownTimeoutSeconds: 10 }] } }))}>添加 Peer Agent</button></div></SettingsField></SettingsCard></div>;
    }
    return (
      <div className="grid gap-6">
        <SettingsCard title="接入配置" summary="先把 NovelAI 的启用状态、Token 和基础地址配好；未启用时整组都不会生效。">
          <SettingsField label="启用 NovelAI" description="总开关关闭时，该组参数不会参与运行。" badge={{ label: draft.integrations.novelaiEnabled ? "已启用" : "未启用", tone: draft.integrations.novelaiEnabled ? "success" : "warning" }} hint={<SettingsFieldHint usage="控制 NovelAI 集成是否启用。" blank="关闭时整组 NovelAI 参数都不会生效。" effect="影响桌面生图相关能力。" configPath="integrations.novelai.enabled" />}><label className="flex items-center gap-3 rounded-[16px] border border-[#E6E9EE] bg-[#FBFBFC] px-4 py-3"><input type="checkbox" checked={draft.integrations.novelaiEnabled} onChange={(event) => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, novelaiEnabled: event.target.checked } }))} /><span>integrations.novelai.enabled</span></label></SettingsField>
          <SettingsField label="NovelAI Token" description="NovelAI 鉴权凭据。" badge={fieldStatus(Boolean(draft.integrations.novelaiToken.trim()), "已配置 Token", "Token 未配置")} hint={<SettingsFieldHint usage="为 NovelAI 请求提供鉴权凭据。" blank="留空时无法完成 NovelAI 鉴权。" effect="影响所有 NovelAI 生图请求。" configPath="integrations.novelai.token" />}><SecretInput value={draft.integrations.novelaiToken} onChange={(value) => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, novelaiToken: value } }))} /></SettingsField>
          <SettingsField label="NovelAI Base URL" description="只在走独立入口或代理时需要改。" badge={{ label: draft.integrations.novelaiBaseUrl.trim() ? "自定义地址" : "使用默认地址", tone: draft.integrations.novelaiBaseUrl.trim() ? "neutral" : "success" }} hint={<SettingsFieldHint usage="覆盖 NovelAI 默认服务地址。" blank="留空时使用默认地址。" effect="影响 NovelAI 请求入口。" configPath="integrations.novelai.base_url" />}><input className={cx(inputClass, "bg-white")} value={draft.integrations.novelaiBaseUrl} onChange={(event) => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, novelaiBaseUrl: event.target.value } }))} placeholder="https://api.novelai.net" /></SettingsField>
        </SettingsCard>
        <SettingsCard title="生成默认值" summary="管理普通模型、NSFW 模型和默认生成偏好，不常改的高级项收进展开区。">
          <SettingsField label="普通模型" description="默认 txt2img / img2img 走的模型。" badge={fieldStatus(Boolean(draft.integrations.novelaiDefaultModel.trim()), "已配置默认模型", "默认模型未配置")} hint={<SettingsFieldHint usage="指定 NovelAI 默认生成模型。" effect="影响普通生图时选择的模型。" configPath="integrations.novelai.default_model" />}><input className={cx(inputClass, "bg-white")} value={draft.integrations.novelaiDefaultModel} onChange={(event) => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, novelaiDefaultModel: event.target.value } }))} /></SettingsField>
          <SettingsField label="NSFW 模型" description="只在 NSFW 模式开启后参与选择。" badge={{ label: draft.integrations.novelaiNsfwEnabled ? "NSFW 依赖此模型" : "仅启用后生效", tone: draft.integrations.novelaiNsfwEnabled ? "success" : "warning" }} hint={<SettingsFieldHint usage="指定 NSFW 路径使用的模型。" blank="未填写时 NSFW 路径无法切换到独立模型。" effect="影响 NSFW 生图时使用的模型。" configPath="integrations.novelai.nsfw_model" />}><input className={cx(inputClass, "bg-white")} value={draft.integrations.novelaiNsfwModel} onChange={(event) => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, novelaiNsfwModel: event.target.value } }))} /></SettingsField>
          <SettingsExpandableBlock>
            <SettingsField label="Add Quality Tags" description="打开后会为默认提示词追加质量标签。" hint={<SettingsFieldHint usage="控制是否自动添加质量标签。" effect="影响默认提示词构造。" configPath="integrations.novelai.add_quality_tags" />}><label className="flex items-center gap-3 rounded-[16px] border border-[#E6E9EE] bg-white px-4 py-3"><input type="checkbox" checked={draft.integrations.novelaiAddQualityTags} onChange={(event) => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, novelaiAddQualityTags: event.target.checked } }))} /><span>Add Quality Tags</span></label></SettingsField>
            <SettingsField label="Undesired Content Preset" description="选择默认反向内容预设。" hint={<SettingsFieldHint usage="设置默认 undesired content 预设。" effect="影响生图默认反向内容强度。" configPath="integrations.novelai.undesired_content_preset" />}><select className={cx(inputClass, "bg-white")} value={String(draft.integrations.novelaiUndesiredContentPreset)} onChange={(event) => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, novelaiUndesiredContentPreset: parseNumber(event.target.value, current.integrations.novelaiUndesiredContentPreset) } }))}><option value="0">None</option><option value="1">Light</option><option value="2">Heavy</option></select></SettingsField>
          </SettingsExpandableBlock>
        </SettingsCard>
        <SettingsCard title="权限与限制" summary="把启用条件、NSFW 依赖关系和资源上限集中展示，避免误以为所有选项都默认生效。">
          <SettingsField label="生成权限" description="分别控制 txt2img 和 img2img 是否可用。" hint={<SettingsFieldHint usage="限制 NovelAI 允许执行的生成模式。" effect="影响用户能否发起文生图或图生图。" />}><div className="grid gap-3 md:grid-cols-2"><label className="flex items-center gap-3 rounded-[16px] border border-[#E6E9EE] bg-[#FBFBFC] px-4 py-3"><input type="checkbox" checked={draft.integrations.novelaiAllowTxt2img} onChange={(event) => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, novelaiAllowTxt2img: event.target.checked } }))} /><span>允许文生图</span></label><label className="flex items-center gap-3 rounded-[16px] border border-[#E6E9EE] bg-[#FBFBFC] px-4 py-3"><input type="checkbox" checked={draft.integrations.novelaiAllowImg2img} onChange={(event) => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, novelaiAllowImg2img: event.target.checked } }))} /><span>允许图生图</span></label></div></SettingsField>
          <SettingsField label="NSFW 与写回" description="NSFW 模式和自动写回角色素材都属于附加行为，不等同于基础 NovelAI 接入。" hint={<SettingsFieldHint usage="控制 NSFW 路径与生成结果写回行为。" blank="关闭时只保留普通模型生图路径。" effect="影响是否切到 NSFW 模型，以及是否把结果写回角色素材。" />}><div className="grid gap-3"><label className="flex items-center gap-3 rounded-[16px] border border-[#E6E9EE] bg-[#FBFBFC] px-4 py-3"><input type="checkbox" checked={draft.integrations.novelaiNsfwEnabled} onChange={(event) => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, novelaiNsfwEnabled: event.target.checked } }))} /><span>启用 NSFW 模式</span></label><label className="flex items-center gap-3 rounded-[16px] border border-[#E6E9EE] bg-[#FBFBFC] px-4 py-3"><input type="checkbox" checked={draft.integrations.novelaiAutoWritebackRoleAssets} onChange={(event) => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, novelaiAutoWritebackRoleAssets: event.target.checked } }))} /><span>生成后自动写回角色素材</span></label></div></SettingsField>
          <SettingsExpandableBlock><SettingsField label="资源上限" description="限制单次最大步数和最大总像素。" hint={<SettingsFieldHint usage="限制单次生成资源开销。" effect="影响 NovelAI 单次生成的耗时和上限。" />}><div className="grid gap-3 md:grid-cols-2"><input className={cx(inputClass, "bg-white")} value={String(draft.integrations.novelaiMaxSteps)} onChange={(event) => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, novelaiMaxSteps: parseNumber(event.target.value, current.integrations.novelaiMaxSteps) } }))} placeholder="最大步数" /><input className={cx(inputClass, "bg-white")} value={String(draft.integrations.novelaiMaxPixels)} onChange={(event) => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, novelaiMaxPixels: parseNumber(event.target.value, current.integrations.novelaiMaxPixels) } }))} placeholder="最大总像素" /></div></SettingsField></SettingsExpandableBlock>
        </SettingsCard>
      </div>
    );
  }
  return null;
}
