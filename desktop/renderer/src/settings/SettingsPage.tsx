import type React from "react";
import { useDeferredValue, useEffect, useState } from "react";
import { type SettingsSectionId, settingsSections } from "./SettingsSidebar";
import {
  cardClass,
  cx,
  ghostButtonClass,
  inputClass,
  panelTitleClass,
  primaryButtonClass,
  textareaClass,
} from "../shared/styles";
import type { SettingsChannelGroup, SettingsFormData, SettingsPeerAgent, SettingsQQBotGroup, SettingsSnapshot } from "../shared/types";

type SavePhase =
  | "idle"
  | "dirty"
  | "saving"
  | "restarting"
  | "saved"
  | "restart-failed"
  | "error";

type SettingsPageProps = {
  bridgeReady: boolean;
  search: string;
  section: SettingsSectionId;
  onMetaChange?: (meta: { configPath: string; dirty: boolean }) => void;
};

function joinLines(values: string[]): string {
  return values.join("\n");
}

function splitLines(value: string): string[] {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function cloneSettings(data: SettingsFormData): SettingsFormData {
  return JSON.parse(JSON.stringify(data)) as SettingsFormData;
}

function parseLauncher(value: string): string[] {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function formatLauncher(values: string[]): string {
  return values.join("\n");
}

function settingsEqual(left: SettingsFormData | null, right: SettingsFormData | null): boolean {
  if (!left || !right) return false;
  return JSON.stringify(left) === JSON.stringify(right);
}

function parseNumber(value: string, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="grid gap-2.5 border-b border-[#ECEEF2] px-5 py-4 last:border-b-0">
      <div className="grid gap-1">
        <div className="text-sm font-medium text-[#171717]">{label}</div>
        {hint ? <div className="text-[12px] leading-5 text-[#7B7F87]">{hint}</div> : null}
      </div>
      {children}
    </div>
  );
}

function SecretInput({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="flex items-center gap-3">
      <input
        className={cx(inputClass, "flex-1 bg-white")}
        type={visible ? "text" : "password"}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      <button
        className={cx("text-sm", ghostButtonClass)}
        type="button"
        onClick={() => setVisible((current) => !current)}
      >
        {visible ? "隐藏" : "显示"}
      </button>
    </div>
  );
}

function SectionCard({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="grid gap-4">
      <div className="grid gap-1.5">
        <h2 className={cx(panelTitleClass, "font-sans text-[30px] text-[#171717]")}>{title}</h2>
        {description ? <p className="m-0 text-sm text-[#72767D]">{description}</p> : null}
      </div>
      <div className={cx(cardClass, "overflow-hidden rounded-[18px] border border-[#E7EAF0] bg-white shadow-[0_10px_28px_rgba(15,23,42,0.04)]")}>
        {children}
      </div>
    </section>
  );
}

export function SettingsPage({ bridgeReady, search, section, onMetaChange }: SettingsPageProps) {
  const [snapshot, setSnapshot] = useState<SettingsSnapshot | null>(null);
  const [draft, setDraft] = useState<SettingsFormData | null>(null);
  const [loadError, setLoadError] = useState("");
  const [phase, setPhase] = useState<SavePhase>("idle");
  const [statusMessage, setStatusMessage] = useState("");
  const deferredSearch = useDeferredValue(search.trim().toLowerCase());

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        if (typeof window.miraDesktop.readSettings !== "function") {
          throw new Error("当前桌面进程版本过旧，请完全关闭并重新打开桌面端。");
        }
        const nextSnapshot = await window.miraDesktop.readSettings();
        if (cancelled) return;
        setSnapshot(nextSnapshot);
        setDraft(cloneSettings(nextSnapshot.formData));
        setLoadError("");
        setPhase("idle");
        setStatusMessage("");
      } catch (error) {
        if (cancelled) return;
        setLoadError(error instanceof Error ? error.message : String(error));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!snapshot || !draft) return;
    setPhase(settingsEqual(snapshot.formData, draft) ? "idle" : "dirty");
  }, [snapshot, draft]);

  useEffect(() => {
    if (!snapshot || !draft) return;
    onMetaChange?.({
      configPath: snapshot.configPath,
      dirty: !settingsEqual(snapshot.formData, draft),
    });
  }, [draft, onMetaChange, snapshot]);

  function updateDraft(mutator: (current: SettingsFormData) => SettingsFormData): void {
    setDraft((current) => {
      if (!current) return current;
      return mutator(cloneSettings(current));
    });
  }

  async function save(): Promise<void> {
    if (!draft) return;
    if (typeof window.miraDesktop.saveSettings !== "function") {
      setPhase("error");
      setStatusMessage("当前桌面进程版本过旧，请完全关闭并重新打开桌面端。");
      return;
    }
    setPhase("saving");
    setStatusMessage("正在写入 config.toml...");
    try {
      const result = await window.miraDesktop.saveSettings(draft);
      if (result.restart.ok) {
        setPhase("saved");
        setStatusMessage(result.health.ok ? "配置已保存，Bridge 已重启。" : `配置已保存，但健康检查失败：${result.health.message}`);
      } else {
        setPhase("restart-failed");
        setStatusMessage(`配置已保存，但 Bridge 重启失败：${result.restart.lastError || "unknown error"}`);
      }
      const nextSnapshot = await window.miraDesktop.readSettings();
      setSnapshot(nextSnapshot);
      setDraft(cloneSettings(nextSnapshot.formData));
    } catch (error) {
      setPhase("error");
      setStatusMessage(error instanceof Error ? error.message : String(error));
    }
  }

  function reset(): void {
    if (!snapshot) return;
    setDraft(cloneSettings(snapshot.formData));
    setStatusMessage("已恢复到当前磁盘配置。");
    setPhase("idle");
  }

  if (loadError) {
    return (
      <section className="settings-page grid h-full place-items-center bg-[#F7F8FB]" data-testid="settings-page">
        <div className={cx(cardClass, "mx-8 max-w-[680px] p-6 text-sm leading-6 text-[#8f2d2d]")}>
          设置加载失败：{loadError}
        </div>
      </section>
    );
  }

  if (!draft) {
    return (
      <section className="settings-page grid h-full place-items-center bg-[#F7F8FB]" data-testid="settings-page">
        <div className="text-sm text-[#737781]">正在加载设置...</div>
      </section>
    );
  }

  const visibleSections = settingsSections.filter((section) => {
    if (!deferredSearch) return true;
    return section.label.toLowerCase().includes(deferredSearch) || section.id.toLowerCase().includes(deferredSearch);
  });
  const currentSection = visibleSections.find((item) => item.id === section) ?? visibleSections[0] ?? null;
  const currentId = currentSection?.id ?? null;

  return (
    <section className="settings-page grid h-full grid-rows-[auto_minmax(0,1fr)] overflow-hidden bg-[#F7F8FB]" data-testid="settings-page">
      <div className="settings-content grid min-h-0 grid-rows-[auto_minmax(0,1fr)] overflow-hidden">
        <div className="border-b border-[#E8EBF0] bg-[#F7F8FB] px-10 py-5">
          <div className="flex items-center justify-between gap-4">
            <div className="grid gap-1">
              <div className="text-sm font-medium text-[#1A1D21]">
                {phase === "idle" && "当前配置已同步"}
                {phase === "dirty" && "有未保存更改"}
                {phase === "saving" && "正在保存"}
                {phase === "restarting" && "正在重启 Bridge"}
                {phase === "saved" && "已保存"}
                {phase === "restart-failed" && "Bridge 重启失败"}
                {phase === "error" && "保存失败"}
              </div>
              <div className="text-[12px] leading-5 text-[#7A7F86]">
                {statusMessage || "包含密钥字段的修改会直接写入本地 config.toml，并在保存后自动重启 Bridge。"}
              </div>
            </div>
            <div className="flex items-center gap-2.5">
              <button className={cx("text-sm", ghostButtonClass)} type="button" onClick={reset}>
                重置
              </button>
              <button className={cx("text-sm", primaryButtonClass)} type="button" onClick={() => void save()} disabled={!bridgeReady || phase === "saving"}>
                保存并重启
              </button>
            </div>
          </div>
        </div>
        <div className="scrollbar-soft overflow-y-auto px-10 py-8">
          <div className="mx-auto w-full max-w-[940px]">
            {!currentSection ? (
              <div className={cx(cardClass, "grid min-h-[240px] place-items-center border-dashed text-sm text-[#7f8490]")}>
                没有匹配的设置项
              </div>
            ) : null}
            {currentId === "models" ? (
              <SectionCard title="模型" description="配置主模型、轻量模型和视觉模型，以及它们各自的密钥与访问地址。">
                <Field label="Provider" hint="当前主模型提供商。">
                  <input className={cx(inputClass, "bg-white")} value={draft.models.provider} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, provider: event.target.value } }))} />
                </Field>
                <Field label="主模型" hint="桌面主对话使用的模型名。">
                  <input className={cx(inputClass, "bg-white")} value={draft.models.mainModel} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, mainModel: event.target.value } }))} />
                </Field>
                <Field label="主模型 API Key">
                  <SecretInput value={draft.models.mainApiKey} onChange={(value) => updateDraft((current) => ({ ...current, models: { ...current.models, mainApiKey: value } }))} />
                </Field>
                <Field label="主模型 Base URL">
                  <input className={cx(inputClass, "bg-white")} value={draft.models.mainBaseUrl} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, mainBaseUrl: event.target.value } }))} />
                </Field>
                <Field label="主模型开关">
                  <div className="grid gap-3 md:grid-cols-2">
                    <label className="flex items-center gap-3 rounded-xl border border-[#E6E9EE] bg-[#FBFBFC] px-4 py-3">
                      <input type="checkbox" checked={draft.models.enableThinking} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, enableThinking: event.target.checked } }))} />
                      <span>启用 Thinking</span>
                    </label>
                    <label className="flex items-center gap-3 rounded-xl border border-[#E6E9EE] bg-[#FBFBFC] px-4 py-3">
                      <input type="checkbox" checked={draft.models.multimodal} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, multimodal: event.target.checked } }))} />
                      <span>启用多模态</span>
                    </label>
                  </div>
                </Field>
                <Field label="轻量模型">
                  <div className="grid gap-3">
                    <input className={cx(inputClass, "bg-white")} value={draft.models.fastModel} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, fastModel: event.target.value } }))} placeholder="模型名" />
                    <SecretInput value={draft.models.fastApiKey} onChange={(value) => updateDraft((current) => ({ ...current, models: { ...current.models, fastApiKey: value } }))} />
                    <input className={cx(inputClass, "bg-white")} value={draft.models.fastBaseUrl} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, fastBaseUrl: event.target.value } }))} placeholder="基础地址" />
                  </div>
                </Field>
                <Field label="视觉模型">
                  <div className="grid gap-3">
                    <input className={cx(inputClass, "bg-white")} value={draft.models.vlModel} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, vlModel: event.target.value } }))} placeholder="模型名" />
                    <SecretInput value={draft.models.vlApiKey} onChange={(value) => updateDraft((current) => ({ ...current, models: { ...current.models, vlApiKey: value } }))} />
                    <input className={cx(inputClass, "bg-white")} value={draft.models.vlBaseUrl} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, vlBaseUrl: event.target.value } }))} placeholder="基础地址" />
                  </div>
                </Field>
              </SectionCard>
            ) : null}

            {currentId === "channels" ? (
              <div className="grid gap-8">
                <SectionCard title="频道" description="配置 Telegram、QQ、QQBot 以及 CLI/socket 的连接信息。">
                  <Field label="Telegram Token">
                    <SecretInput value={draft.channels.telegramToken} onChange={(value) => updateDraft((current) => ({ ...current, channels: { ...current.channels, telegramToken: value } }))} />
                  </Field>
                  <Field label="Telegram Allow From" hint="每行一个用户名，不带 @。">
                    <textarea className={cx(textareaClass, "min-h-20 bg-white")} value={joinLines(draft.channels.telegramAllowFrom)} onChange={(event) => updateDraft((current) => ({ ...current, channels: { ...current.channels, telegramAllowFrom: splitLines(event.target.value) } }))} />
                  </Field>
                  <Field label="Telegram Channel Name">
                    <input className={cx(inputClass, "bg-white")} value={draft.channels.telegramChannelName} onChange={(event) => updateDraft((current) => ({ ...current, channels: { ...current.channels, telegramChannelName: event.target.value } }))} />
                  </Field>
                  <Field label="QQ Bot UIN">
                    <input className={cx(inputClass, "bg-white")} value={draft.channels.qqBotUin} onChange={(event) => updateDraft((current) => ({ ...current, channels: { ...current.channels, qqBotUin: event.target.value } }))} />
                  </Field>
                  <Field label="QQ Allow From" hint="每行一个 QQ 号。">
                    <textarea className={cx(textareaClass, "min-h-20 bg-white")} value={joinLines(draft.channels.qqAllowFrom)} onChange={(event) => updateDraft((current) => ({ ...current, channels: { ...current.channels, qqAllowFrom: splitLines(event.target.value) } }))} />
                  </Field>
                  <Field label="QQ WebSocket 超时秒数">
                    <input className={cx(inputClass, "bg-white")} value={String(draft.channels.qqWebsocketOpenTimeoutSeconds)} onChange={(event) => updateDraft((current) => ({ ...current, channels: { ...current.channels, qqWebsocketOpenTimeoutSeconds: parseNumber(event.target.value, current.channels.qqWebsocketOpenTimeoutSeconds) } }))} />
                  </Field>
                  <Field label="QQ 群组规则" hint="第一版先用逐条卡片编辑。">
                    <div className="grid gap-3">
                      {draft.channels.qqGroups.map((group, index) => (
                        <GroupEditor
                          key={`${group.groupId}-${index}`}
                          group={group}
                          onChange={(nextGroup) => updateDraft((current) => {
                            const next = [...current.channels.qqGroups];
                            next[index] = nextGroup;
                            return { ...current, channels: { ...current.channels, qqGroups: next } };
                          })}
                          onRemove={() => updateDraft((current) => ({
                            ...current,
                            channels: {
                              ...current.channels,
                              qqGroups: current.channels.qqGroups.filter((_, groupIndex) => groupIndex !== index),
                            },
                          }))}
                        />
                      ))}
                      <button className={cx("text-sm", ghostButtonClass)} type="button" onClick={() => updateDraft((current) => ({
                        ...current,
                        channels: {
                          ...current.channels,
                          qqGroups: [...current.channels.qqGroups, { groupId: "", allowFrom: [], requireAt: true }],
                        },
                      }))}>
                        添加 QQ 群组
                      </button>
                    </div>
                  </Field>
                  <Field label="QQBot App ID">
                    <input className={cx(inputClass, "bg-white")} value={draft.channels.qqbotAppId} onChange={(event) => updateDraft((current) => ({ ...current, channels: { ...current.channels, qqbotAppId: event.target.value } }))} />
                  </Field>
                  <Field label="QQBot Client Secret">
                    <SecretInput value={draft.channels.qqbotClientSecret} onChange={(value) => updateDraft((current) => ({ ...current, channels: { ...current.channels, qqbotClientSecret: value } }))} />
                  </Field>
                  <Field label="QQBot Allow From" hint="每行一个 user_openid。">
                    <textarea className={cx(textareaClass, "min-h-20 bg-white")} value={joinLines(draft.channels.qqbotAllowFrom)} onChange={(event) => updateDraft((current) => ({ ...current, channels: { ...current.channels, qqbotAllowFrom: splitLines(event.target.value) } }))} />
                  </Field>
                  <Field label="QQBot 群组规则">
                    <div className="grid gap-3">
                      {draft.channels.qqbotGroups.map((group, index) => (
                        <QQBotGroupEditor
                          key={`${group.groupOpenid}-${index}`}
                          group={group}
                          onChange={(nextGroup) => updateDraft((current) => {
                            const next = [...current.channels.qqbotGroups];
                            next[index] = nextGroup;
                            return { ...current, channels: { ...current.channels, qqbotGroups: next } };
                          })}
                          onRemove={() => updateDraft((current) => ({
                            ...current,
                            channels: {
                              ...current.channels,
                              qqbotGroups: current.channels.qqbotGroups.filter((_, groupIndex) => groupIndex !== index),
                            },
                          }))}
                        />
                      ))}
                      <button className={cx("text-sm", ghostButtonClass)} type="button" onClick={() => updateDraft((current) => ({
                        ...current,
                        channels: {
                          ...current.channels,
                          qqbotGroups: [...current.channels.qqbotGroups, { groupOpenid: "", allowFrom: [], requireAt: true, allowProactive: false }],
                        },
                      }))}>
                        添加 QQBot 群组
                      </button>
                    </div>
                  </Field>
                  <Field label="CLI Socket">
                    <input className={cx(inputClass, "bg-white")} value={draft.channels.cliSocket} onChange={(event) => updateDraft((current) => ({ ...current, channels: { ...current.channels, cliSocket: event.target.value } }))} />
                  </Field>
                  <Field label="CLI Session Key">
                    <input className={cx(inputClass, "bg-white")} value={draft.channels.cliSessionKey} onChange={(event) => updateDraft((current) => ({ ...current, channels: { ...current.channels, cliSessionKey: event.target.value } }))} />
                  </Field>
                </SectionCard>
              </div>
            ) : null}

            {currentId === "memory" ? (
              <SectionCard title="记忆" description="配置语义记忆开关、引擎和 embedding 模型。">
                <Field label="启用记忆">
                  <label className="flex items-center gap-3 rounded-xl border border-[#E6E9EE] bg-[#FBFBFC] px-4 py-3">
                    <input type="checkbox" checked={draft.memory.enabled} onChange={(event) => updateDraft((current) => ({ ...current, memory: { ...current.memory, enabled: event.target.checked } }))} />
                    <span>memory.enabled</span>
                  </label>
                </Field>
                <Field label="记忆引擎">
                  <input className={cx(inputClass, "bg-white")} value={draft.memory.engine} onChange={(event) => updateDraft((current) => ({ ...current, memory: { ...current.memory, engine: event.target.value } }))} />
                </Field>
                <Field label="Embedding 模型">
                  <input className={cx(inputClass, "bg-white")} value={draft.memory.embeddingModel} onChange={(event) => updateDraft((current) => ({ ...current, memory: { ...current.memory, embeddingModel: event.target.value } }))} />
                </Field>
                <Field label="Embedding API Key">
                  <SecretInput value={draft.memory.embeddingApiKey} onChange={(value) => updateDraft((current) => ({ ...current, memory: { ...current.memory, embeddingApiKey: value } }))} />
                </Field>
                <Field label="Embedding 基础地址">
                  <input className={cx(inputClass, "bg-white")} value={draft.memory.embeddingBaseUrl} onChange={(event) => updateDraft((current) => ({ ...current, memory: { ...current.memory, embeddingBaseUrl: event.target.value } }))} />
                </Field>
                <Field label="输出维度" hint="留空表示不写该字段。">
                  <input className={cx(inputClass, "bg-white")} value={draft.memory.outputDimensionality} onChange={(event) => updateDraft((current) => ({ ...current, memory: { ...current.memory, outputDimensionality: event.target.value } }))} />
                </Field>
              </SectionCard>
            ) : null}

            {currentId === "proactive" ? (
              <SectionCard title="主动推送" description="配置 proactive 总开关、目标、agent 和 drift。">
                <Field label="启用主动推送">
                  <label className="flex items-center gap-3 rounded-xl border border-[#E6E9EE] bg-[#FBFBFC] px-4 py-3">
                    <input type="checkbox" checked={draft.proactive.enabled} onChange={(event) => updateDraft((current) => ({ ...current, proactive: { ...current.proactive, enabled: event.target.checked } }))} />
                    <span>proactive.enabled</span>
                  </label>
                </Field>
                <Field label="配置档">
                  <input className={cx(inputClass, "bg-white")} value={draft.proactive.profile} onChange={(event) => updateDraft((current) => ({ ...current, proactive: { ...current.proactive, profile: event.target.value } }))} />
                </Field>
                <Field label="目标频道与 Chat ID">
                  <div className="grid gap-3 md:grid-cols-2">
                    <input className={cx(inputClass, "bg-white")} value={draft.proactive.targetChannel} onChange={(event) => updateDraft((current) => ({ ...current, proactive: { ...current.proactive, targetChannel: event.target.value } }))} placeholder="频道名" />
                    <input className={cx(inputClass, "bg-white")} value={draft.proactive.targetChatId} onChange={(event) => updateDraft((current) => ({ ...current, proactive: { ...current.proactive, targetChatId: event.target.value } }))} placeholder="会话 ID" />
                  </div>
                </Field>
                <Field label="Agent 参数">
                  <div className="grid gap-3 md:grid-cols-2">
                    <input className={cx(inputClass, "bg-white")} value={String(draft.proactive.agentMaxSteps)} onChange={(event) => updateDraft((current) => ({ ...current, proactive: { ...current.proactive, agentMaxSteps: parseNumber(event.target.value, current.proactive.agentMaxSteps) } }))} placeholder="最大步数" />
                    <input className={cx(inputClass, "bg-white")} value={String(draft.proactive.agentContentLimit)} onChange={(event) => updateDraft((current) => ({ ...current, proactive: { ...current.proactive, agentContentLimit: parseNumber(event.target.value, current.proactive.agentContentLimit) } }))} placeholder="内容长度限制" />
                    <input className={cx(inputClass, "bg-white")} value={String(draft.proactive.agentWebFetchMaxChars)} onChange={(event) => updateDraft((current) => ({ ...current, proactive: { ...current.proactive, agentWebFetchMaxChars: parseNumber(event.target.value, current.proactive.agentWebFetchMaxChars) } }))} placeholder="网页抓取最大字符数" />
                    <input className={cx(inputClass, "bg-white")} value={String(draft.proactive.agentContextProb)} onChange={(event) => updateDraft((current) => ({ ...current, proactive: { ...current.proactive, agentContextProb: parseNumber(event.target.value, current.proactive.agentContextProb) } }))} placeholder="上下文概率" />
                    <input className={cx(inputClass, "bg-white")} value={String(draft.proactive.agentDeliveryCooldownHours)} onChange={(event) => updateDraft((current) => ({ ...current, proactive: { ...current.proactive, agentDeliveryCooldownHours: parseNumber(event.target.value, current.proactive.agentDeliveryCooldownHours) } }))} placeholder="发送冷却小时数" />
                  </div>
                </Field>
                <Field label="Drift">
                  <div className="grid gap-3">
                    <label className="flex items-center gap-3 rounded-xl border border-[#E6E9EE] bg-[#FBFBFC] px-4 py-3">
                      <input type="checkbox" checked={draft.proactive.driftEnabled} onChange={(event) => updateDraft((current) => ({ ...current, proactive: { ...current.proactive, driftEnabled: event.target.checked } }))} />
                      <span>proactive.drift.enabled</span>
                    </label>
                    <div className="grid gap-3 md:grid-cols-2">
                      <input className={cx(inputClass, "bg-white")} value={String(draft.proactive.driftMaxSteps)} onChange={(event) => updateDraft((current) => ({ ...current, proactive: { ...current.proactive, driftMaxSteps: parseNumber(event.target.value, current.proactive.driftMaxSteps) } }))} placeholder="最大步数" />
                      <input className={cx(inputClass, "bg-white")} value={String(draft.proactive.driftMinIntervalHours)} onChange={(event) => updateDraft((current) => ({ ...current, proactive: { ...current.proactive, driftMinIntervalHours: parseNumber(event.target.value, current.proactive.driftMinIntervalHours) } }))} placeholder="最小间隔小时数" />
                    </div>
                  </div>
                </Field>
              </SectionCard>
            ) : null}

            {currentId === "integrations" ? (
              <SectionCard title="集成" description="当前先覆盖 Fitbit 和 Peer Agents。">
                <Field label="Fitbit">
                  <label className="flex items-center gap-3 rounded-xl border border-[#E6E9EE] bg-[#FBFBFC] px-4 py-3">
                    <input type="checkbox" checked={draft.integrations.fitbitEnabled} onChange={(event) => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, fitbitEnabled: event.target.checked } }))} />
                    <span>integrations.fitbit.enabled</span>
                  </label>
                </Field>
                <Field label="Peer Agents">
                  <div className="grid gap-3">
                    {draft.integrations.peerAgents.map((agent, index) => (
                      <PeerAgentEditor
                        key={`${agent.name}-${index}`}
                        agent={agent}
                        onChange={(nextAgent) => updateDraft((current) => {
                          const next = [...current.integrations.peerAgents];
                          next[index] = nextAgent;
                          return { ...current, integrations: { ...current.integrations, peerAgents: next } };
                        })}
                        onRemove={() => updateDraft((current) => ({
                          ...current,
                          integrations: {
                            ...current.integrations,
                            peerAgents: current.integrations.peerAgents.filter((_, agentIndex) => agentIndex !== index),
                          },
                        }))}
                      />
                    ))}
                    <button className={cx("text-sm", ghostButtonClass)} type="button" onClick={() => updateDraft((current) => ({
                      ...current,
                      integrations: {
                        ...current.integrations,
                        peerAgents: [
                          ...current.integrations.peerAgents,
                          {
                            name: "",
                            baseUrl: "",
                            launcher: [],
                            cwd: "",
                            description: "",
                            healthPath: "/health",
                            startupTimeoutSeconds: 30,
                            shutdownTimeoutSeconds: 10,
                          },
                        ],
                      },
                    }))}>
                      添加 Peer Agent
                    </button>
                  </div>
                </Field>
              </SectionCard>
            ) : null}

            {currentId === "advanced" ? (
              <SectionCard title="高级" description="包含不常改但仍然可编辑的全局配置项。">
                <Field label="全局基础 Prompt" hint="这是 config.toml 里的 agent.system_prompt，不是角色 prompt。">
                  <textarea className={cx(textareaClass, "min-h-28 bg-white")} value={draft.advanced.systemPrompt} onChange={(event) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, systemPrompt: event.target.value } }))} />
                </Field>
                <Field label="全局数值项">
                  <div className="grid gap-3 md:grid-cols-2">
                    <input className={cx(inputClass, "bg-white")} value={String(draft.advanced.maxTokens)} onChange={(event) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, maxTokens: parseNumber(event.target.value, current.advanced.maxTokens) } }))} placeholder="最大令牌数" />
                    <input className={cx(inputClass, "bg-white")} value={String(draft.advanced.maxIterations)} onChange={(event) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, maxIterations: parseNumber(event.target.value, current.advanced.maxIterations) } }))} placeholder="最大迭代次数" />
                    <input className={cx(inputClass, "bg-white")} value={String(draft.advanced.memoryWindow)} onChange={(event) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, memoryWindow: parseNumber(event.target.value, current.advanced.memoryWindow) } }))} placeholder="记忆窗口大小" />
                    <input className={cx(inputClass, "bg-white")} value={String(draft.advanced.memoryOptimizerIntervalSeconds)} onChange={(event) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, memoryOptimizerIntervalSeconds: parseNumber(event.target.value, current.advanced.memoryOptimizerIntervalSeconds) } }))} placeholder="记忆优化间隔秒数" />
                  </div>
                </Field>
                <Field label="高级开关">
                  <div className="grid gap-3 md:grid-cols-2">
                    <label className="flex items-center gap-3 rounded-xl border border-[#E6E9EE] bg-[#FBFBFC] px-4 py-3">
                      <input type="checkbox" checked={draft.advanced.devMode} onChange={(event) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, devMode: event.target.checked } }))} />
                      <span>dev_mode</span>
                    </label>
                    <label className="flex items-center gap-3 rounded-xl border border-[#E6E9EE] bg-[#FBFBFC] px-4 py-3">
                      <input type="checkbox" checked={draft.advanced.searchEnabled} onChange={(event) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, searchEnabled: event.target.checked } }))} />
                      <span>search_enabled</span>
                    </label>
                    <label className="flex items-center gap-3 rounded-xl border border-[#E6E9EE] bg-[#FBFBFC] px-4 py-3">
                      <input type="checkbox" checked={draft.advanced.spawnEnabled} onChange={(event) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, spawnEnabled: event.target.checked } }))} />
                      <span>spawn_enabled</span>
                    </label>
                    <label className="flex items-center gap-3 rounded-xl border border-[#E6E9EE] bg-[#FBFBFC] px-4 py-3">
                      <input type="checkbox" checked={draft.advanced.memoryOptimizerEnabled} onChange={(event) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, memoryOptimizerEnabled: event.target.checked } }))} />
                      <span>memory_optimizer_enabled</span>
                    </label>
                  </div>
                </Field>
                <Field label="Wiring">
                  <div className="grid gap-3">
                    <input className={cx(inputClass, "bg-white")} value={draft.advanced.wiringContext} onChange={(event) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, wiringContext: event.target.value } }))} placeholder="上下文实现名" />
                    <input className={cx(inputClass, "bg-white")} value={draft.advanced.wiringMemory} onChange={(event) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, wiringMemory: event.target.value } }))} placeholder="记忆实现名" />
                    <textarea className={cx(textareaClass, "min-h-20 bg-white")} value={joinLines(draft.advanced.wiringToolsets)} onChange={(event) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, wiringToolsets: splitLines(event.target.value) } }))} placeholder="每行一个工具集名称" />
                  </div>
                </Field>
                <Field label="其他插件配置" hint="保留给尚未表单化的 plugins.* 段。按 TOML 片段填写。">
                  <textarea className={cx(textareaClass, "min-h-[240px] bg-white font-mono text-[12px]")} value={draft.advanced.pluginsRawToml} onChange={(event) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, pluginsRawToml: event.target.value } }))} />
                </Field>
              </SectionCard>
            ) : null}
          </div>
        </div>
      </div>
    </section>
  );
}

function GroupEditor({
  group,
  onChange,
  onRemove,
}: {
  group: SettingsChannelGroup;
  onChange: (next: SettingsChannelGroup) => void;
  onRemove: () => void;
}) {
  return (
    <div className="grid gap-3 rounded-2xl border border-[#E7EAF0] bg-[#FBFBFC] p-4">
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium text-[#20242A]">QQ 群组</div>
        <button className="text-sm text-[#A14D32]" type="button" onClick={onRemove}>删除</button>
      </div>
      <input className={cx(inputClass, "bg-white")} value={group.groupId} onChange={(event) => onChange({ ...group, groupId: event.target.value })} placeholder="群组 ID" />
      <textarea className={cx(textareaClass, "min-h-16 bg-white")} value={joinLines(group.allowFrom)} onChange={(event) => onChange({ ...group, allowFrom: splitLines(event.target.value) })} placeholder="每行一个允许来源" />
      <label className="flex items-center gap-3 text-sm text-[#4A4F57]">
        <input type="checkbox" checked={group.requireAt} onChange={(event) => onChange({ ...group, requireAt: event.target.checked })} />
        <span>require_at</span>
      </label>
    </div>
  );
}

function QQBotGroupEditor({
  group,
  onChange,
  onRemove,
}: {
  group: SettingsQQBotGroup;
  onChange: (next: SettingsQQBotGroup) => void;
  onRemove: () => void;
}) {
  return (
    <div className="grid gap-3 rounded-2xl border border-[#E7EAF0] bg-[#FBFBFC] p-4">
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium text-[#20242A]">QQBot 群组</div>
        <button className="text-sm text-[#A14D32]" type="button" onClick={onRemove}>删除</button>
      </div>
      <input className={cx(inputClass, "bg-white")} value={group.groupOpenid} onChange={(event) => onChange({ ...group, groupOpenid: event.target.value })} placeholder="群组 OpenID" />
      <textarea className={cx(textareaClass, "min-h-16 bg-white")} value={joinLines(group.allowFrom)} onChange={(event) => onChange({ ...group, allowFrom: splitLines(event.target.value) })} placeholder="每行一个允许来源" />
      <div className="grid gap-3 md:grid-cols-2">
        <label className="flex items-center gap-3 text-sm text-[#4A4F57]">
          <input type="checkbox" checked={group.requireAt} onChange={(event) => onChange({ ...group, requireAt: event.target.checked })} />
          <span>require_at</span>
        </label>
        <label className="flex items-center gap-3 text-sm text-[#4A4F57]">
          <input type="checkbox" checked={group.allowProactive} onChange={(event) => onChange({ ...group, allowProactive: event.target.checked })} />
          <span>allow_proactive</span>
        </label>
      </div>
    </div>
  );
}

function PeerAgentEditor({
  agent,
  onChange,
  onRemove,
}: {
  agent: SettingsPeerAgent;
  onChange: (next: SettingsPeerAgent) => void;
  onRemove: () => void;
}) {
  return (
    <div className="grid gap-3 rounded-2xl border border-[#E7EAF0] bg-[#FBFBFC] p-4">
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium text-[#20242A]">Peer Agent</div>
        <button className="text-sm text-[#A14D32]" type="button" onClick={onRemove}>删除</button>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <input className={cx(inputClass, "bg-white")} value={agent.name} onChange={(event) => onChange({ ...agent, name: event.target.value })} placeholder="名称" />
        <input className={cx(inputClass, "bg-white")} value={agent.baseUrl} onChange={(event) => onChange({ ...agent, baseUrl: event.target.value })} placeholder="基础地址" />
        <input className={cx(inputClass, "bg-white")} value={agent.cwd} onChange={(event) => onChange({ ...agent, cwd: event.target.value })} placeholder="工作目录" />
        <input className={cx(inputClass, "bg-white")} value={agent.healthPath} onChange={(event) => onChange({ ...agent, healthPath: event.target.value })} placeholder="健康检查路径" />
        <input className={cx(inputClass, "bg-white")} value={String(agent.startupTimeoutSeconds)} onChange={(event) => onChange({ ...agent, startupTimeoutSeconds: parseNumber(event.target.value, agent.startupTimeoutSeconds) })} placeholder="启动超时秒数" />
        <input className={cx(inputClass, "bg-white")} value={String(agent.shutdownTimeoutSeconds)} onChange={(event) => onChange({ ...agent, shutdownTimeoutSeconds: parseNumber(event.target.value, agent.shutdownTimeoutSeconds) })} placeholder="关闭超时秒数" />
      </div>
      <textarea className={cx(textareaClass, "min-h-16 bg-white")} value={agent.description} onChange={(event) => onChange({ ...agent, description: event.target.value })} placeholder="描述" />
      <textarea className={cx(textareaClass, "min-h-24 bg-white font-mono text-[12px]")} value={formatLauncher(agent.launcher)} onChange={(event) => onChange({ ...agent, launcher: parseLauncher(event.target.value) })} placeholder="每行一个启动命令片段" />
    </div>
  );
}
