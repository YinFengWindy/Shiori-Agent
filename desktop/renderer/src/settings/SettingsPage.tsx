import type React from "react";
import { useDeferredValue, useEffect, useState } from "react";
import { type SettingsSectionId, settingsSections } from "./SettingsSidebar";
import {
  cardClass,
  cx,
  ghostButtonClass,
  inputClass,
  textareaClass,
} from "../shared/styles";
import { ResetIcon, SaveIcon } from "../shared/icons";
import type {
  RoleRecord,
  SettingsChannelGroup,
  SettingsChannelRoleBinding,
  SettingsFormData,
  SettingsPeerAgent,
  SettingsQQBotGroup,
  SettingsSnapshot,
} from "../shared/types";

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

function getBindingChatIdMeta(channel: string): { label: string; placeholder: string; hint: string } {
  switch (channel) {
    case "telegram":
      return {
        label: "Telegram Chat ID",
        placeholder: "例如 123456789",
        hint: "通常填 Telegram user id 或群 chat_id。",
      };
    case "qq":
      return {
        label: "QQ Chat ID",
        placeholder: "例如好友 QQ 号或群号",
        hint: "和运行时 transport 使用的 chat_id 保持一致。",
      };
    case "qqbot":
      return {
        label: "QQBot Chat ID",
        placeholder: "例如 c2c:USER_OPENID",
        hint: "私聊常用 c2c:USER_OPENID；如果后续支持群，再填对应 group 标识。",
      };
    case "feishu":
      return {
        label: "Feishu Chat ID",
        placeholder: "例如 open_id / chat_id",
        hint: "填入运行时实际使用的 open_id 或 chat_id。",
      };
    case "cli":
      return {
        label: "CLI Session Key",
        placeholder: "例如 local 或 cli:local",
        hint: "用于把特定 CLI 会话固定路由到某个角色。",
      };
    default:
      return {
        label: "Chat ID",
        placeholder: "输入 transport chat_id",
        hint: "填入该渠道实际使用的 chat_id。",
      };
  }
}

function getMemoryEngineOptions(currentValue: string): Array<{ value: string; label: string }> {
  const normalized = currentValue.trim();
  const options = [
    { value: "", label: "default" },
  ];
  if (normalized && normalized !== "default") {
    options.push({ value: normalized, label: normalized });
  }
  return options;
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
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <section>
      <div className={cx(cardClass, "overflow-hidden rounded-[18px] border border-[#E7EAF0] bg-white shadow-[0_10px_28px_rgba(15,23,42,0.04)]")}>
        {children}
      </div>
    </section>
  );
}

const settingsSubsections: Record<SettingsSectionId, Array<{ id: string; label: string }>> = {
  models: [
    { id: "main", label: "主模型" },
    { id: "fast", label: "轻量模型" },
    { id: "vl", label: "视觉模型" },
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
    { id: "general", label: "基础" },
    { id: "target", label: "目标" },
    { id: "agent", label: "Agent 参数" },
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

function createInitialSubsectionState(): Record<SettingsSectionId, string> {
  return {
    models: settingsSubsections.models[0]?.id ?? "",
    channels: settingsSubsections.channels[0]?.id ?? "",
    memory: settingsSubsections.memory[0]?.id ?? "",
    proactive: settingsSubsections.proactive[0]?.id ?? "",
    integrations: settingsSubsections.integrations[0]?.id ?? "",
    advanced: settingsSubsections.advanced[0]?.id ?? "",
  };
}

export function SettingsPage({ bridgeReady, search, section, onMetaChange }: SettingsPageProps) {
  const [snapshot, setSnapshot] = useState<SettingsSnapshot | null>(null);
  const [draft, setDraft] = useState<SettingsFormData | null>(null);
  const [roles, setRoles] = useState<RoleRecord[]>([]);
  const [loadError, setLoadError] = useState("");
  const [savePhase, setSavePhase] = useState<Exclude<SavePhase, "dirty">>("idle");
  const [statusMessage, setStatusMessage] = useState("");
  const [activeSubsections, setActiveSubsections] = useState<Record<SettingsSectionId, string>>(createInitialSubsectionState);
  const deferredSearch = useDeferredValue(search.trim().toLowerCase());
  const floatingActionClass =
    "grid h-10 w-10 place-items-center rounded-full border bg-white/90 shadow-[0_8px_24px_rgba(15,23,42,0.08)] transition duration-200 hover:-translate-y-0.5 disabled:translate-y-0 disabled:cursor-default disabled:border-black/6 disabled:bg-white/60 disabled:text-[#b8b8b8] disabled:shadow-none";

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        if (typeof window.miraDesktop.readSettings !== "function") {
          throw new Error("当前桌面进程版本过旧，请完全关闭并重新打开桌面端。");
        }
        const [nextSnapshot, nextBindings, rolesResponse] = await Promise.all([
          window.miraDesktop.readSettings(),
          window.miraDesktop.readChannelRoleBindings(),
          window.miraDesktop.invoke({
            method: "roles.list",
            payload: {},
          }),
        ]);
        if (cancelled) return;
        const nextFormData = cloneSettings(nextSnapshot.formData);
        nextFormData.channels.roleBindings = nextBindings.bindings;
        if (rolesResponse.error) {
          throw new Error(rolesResponse.error.message);
        }
        setSnapshot(nextSnapshot);
        setDraft(nextFormData);
        setRoles(Array.isArray(rolesResponse.payload.roles) ? rolesResponse.payload.roles as RoleRecord[] : []);
        setLoadError("");
        setSavePhase("idle");
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
    onMetaChange?.({
      configPath: snapshot.configPath,
      dirty: !settingsEqual(snapshot.formData, draft),
    });
  }, [draft, onMetaChange, snapshot]);

  useEffect(() => {
    if (savePhase !== "saved" && savePhase !== "restart-failed" && savePhase !== "error") return;
    const timeoutMs = savePhase === "saved" ? 2200 : 4200;
    const timer = window.setTimeout(() => {
      setStatusMessage("");
      setSavePhase((current) => (current === "saved" || current === "restart-failed" || current === "error" ? "idle" : current));
    }, timeoutMs);
    return () => window.clearTimeout(timer);
  }, [savePhase]);

  function updateDraft(mutator: (current: SettingsFormData) => SettingsFormData): void {
    setDraft((current) => {
      if (!current) return current;
      return mutator(cloneSettings(current));
    });
  }

  async function save(): Promise<void> {
    if (!draft) return;
    if (typeof window.miraDesktop.saveSettings !== "function") {
      setSavePhase("error");
      setStatusMessage("当前桌面进程版本过旧，请完全关闭并重新打开桌面端。");
      return;
    }
    setSavePhase("saving");
    setStatusMessage("正在写入 config.toml...");
    try {
      const [result] = await Promise.all([
        window.miraDesktop.saveSettings(draft),
        window.miraDesktop.saveChannelRoleBindings(draft.channels.roleBindings),
      ]);
      if (result.restart.ok) {
        setSavePhase("saved");
        setStatusMessage(result.health.ok ? "配置已保存，Bridge 已重启。" : `配置已保存，但健康检查失败：${result.health.message}`);
      } else {
        setSavePhase("restart-failed");
        setStatusMessage(`配置已保存，但 Bridge 重启失败：${result.restart.lastError || "unknown error"}`);
      }
      const [nextSnapshot, nextBindings] = await Promise.all([
        window.miraDesktop.readSettings(),
        window.miraDesktop.readChannelRoleBindings(),
      ]);
      const nextFormData = cloneSettings(nextSnapshot.formData);
      nextFormData.channels.roleBindings = nextBindings.bindings;
      setSnapshot(nextSnapshot);
      setDraft(nextFormData);
    } catch (error) {
      setSavePhase("error");
      setStatusMessage(error instanceof Error ? error.message : String(error));
    }
  }

  function reset(): void {
    if (!snapshot) return;
    const nextDraft = cloneSettings(snapshot.formData);
    nextDraft.channels.roleBindings = draft?.channels.roleBindings ?? [];
    setDraft(nextDraft);
    setStatusMessage("");
    setSavePhase("idle");
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

  const formData = draft;
  const visibleSections = settingsSections.filter((section) => {
    if (!deferredSearch) return true;
    return section.label.toLowerCase().includes(deferredSearch) || section.id.toLowerCase().includes(deferredSearch);
  });
  const currentSection = visibleSections.find((item) => item.id === section) ?? visibleSections[0] ?? null;
  const currentId = currentSection?.id ?? null;
  const isDirty = Boolean(snapshot && draft && !settingsEqual(snapshot.formData, draft));
  const visibleSubsections = currentId ? settingsSubsections[currentId] : [];
  const currentSubsectionId = currentId
    ? (visibleSubsections.some((item) => item.id === activeSubsections[currentId])
      ? activeSubsections[currentId]
      : (visibleSubsections[0]?.id ?? null))
    : null;

  function updateActiveSubsection(nextId: string): void {
    if (!currentId) return;
    setActiveSubsections((current) => (
      current[currentId] === nextId
        ? current
        : { ...current, [currentId]: nextId }
    ));
  }

  function renderCurrentSectionContent(): React.ReactNode {
    if (!currentId || !currentSubsectionId) return null;
    const draft = formData;

    function renderRoleBindingsForChannel(channel: SettingsChannelRoleBinding["channel"]): React.ReactNode {
      const bindings = draft.channels.roleBindings
        .map((binding, index) => ({ binding, index }))
        .filter((entry) => entry.binding.channel === channel);

      return (
        <Field label="角色绑定" hint="把当前频道里的具体会话身份绑定到角色。">
          <div className="grid gap-3">
            {bindings.length ? bindings.map(({ binding, index }) => (
              <ChannelRoleBindingEditor
                channel={channel}
                key={`${binding.channel}-${binding.chatId}-${index}`}
                binding={binding}
                roles={roles}
                onChange={(nextBinding) => updateDraft((current) => {
                  const nextBindings = [...current.channels.roleBindings];
                  nextBindings[index] = nextBinding;
                  return {
                    ...current,
                    channels: { ...current.channels, roleBindings: nextBindings },
                  };
                })}
                onRemove={() => updateDraft((current) => ({
                  ...current,
                  channels: {
                    ...current.channels,
                    roleBindings: current.channels.roleBindings.filter((_, bindingIndex) => bindingIndex !== index),
                  },
                }))}
              />
            )) : (
              <div className="rounded-2xl border border-dashed border-[#D8DCE2] bg-[#FBFBFC] px-4 py-3 text-sm text-[#737781]">
                当前频道还没有角色绑定。
              </div>
            )}
            <button className={cx("text-sm", ghostButtonClass)} type="button" onClick={() => updateDraft((current) => ({
              ...current,
              channels: {
                ...current.channels,
                roleBindings: [...current.channels.roleBindings, { channel, chatId: "", roleId: "" }],
              },
            }))}>
              添加角色绑定
            </button>
          </div>
        </Field>
      );
    }

    switch (currentId) {
      case "models":
        switch (currentSubsectionId) {
          case "main":
            return (
              <SectionCard>
                <Field label="Provider" hint="当前主模型提供商。">
                  <input className={cx(inputClass, "bg-white")} value={formData.models.provider} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, provider: event.target.value } }))} />
                </Field>
                <Field label="主模型" hint="桌面主对话使用的模型名。">
                  <input className={cx(inputClass, "bg-white")} value={formData.models.mainModel} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, mainModel: event.target.value } }))} />
                </Field>
                <Field label="主模型 API Key">
                  <SecretInput value={formData.models.mainApiKey} onChange={(value) => updateDraft((current) => ({ ...current, models: { ...current.models, mainApiKey: value } }))} />
                </Field>
                <Field label="主模型 Base URL">
                  <input className={cx(inputClass, "bg-white")} value={formData.models.mainBaseUrl} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, mainBaseUrl: event.target.value } }))} />
                </Field>
                <Field label="Reasoning Effort" hint="支持的模型可用，用于控制推理强度；留空表示不写入。">
                  <input className={cx(inputClass, "bg-white")} value={formData.models.reasoningEffort} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, reasoningEffort: event.target.value } }))} placeholder="例如 low / medium / high" />
                </Field>
                <Field label="主模型开关">
                  <div className="grid gap-3 md:grid-cols-2">
                    <label className="flex items-center gap-3 rounded-xl border border-[#E6E9EE] bg-[#FBFBFC] px-4 py-3">
                      <input type="checkbox" checked={formData.models.enableThinking} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, enableThinking: event.target.checked } }))} />
                      <span>启用 Thinking</span>
                    </label>
                    <label className="flex items-center gap-3 rounded-xl border border-[#E6E9EE] bg-[#FBFBFC] px-4 py-3">
                      <input type="checkbox" checked={formData.models.multimodal} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, multimodal: event.target.checked } }))} />
                      <span>启用多模态</span>
                    </label>
                  </div>
                </Field>
              </SectionCard>
            );
          case "fast":
            return (
              <SectionCard>
                <Field label="轻量模型">
                  <div className="grid gap-3">
                    <input className={cx(inputClass, "bg-white")} value={formData.models.fastModel} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, fastModel: event.target.value } }))} placeholder="模型名" />
                    <SecretInput value={formData.models.fastApiKey} onChange={(value) => updateDraft((current) => ({ ...current, models: { ...current.models, fastApiKey: value } }))} />
                    <input className={cx(inputClass, "bg-white")} value={formData.models.fastBaseUrl} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, fastBaseUrl: event.target.value } }))} placeholder="基础地址" />
                  </div>
                </Field>
              </SectionCard>
            );
          case "vl":
            return (
              <SectionCard>
                <Field label="视觉模型">
                  <div className="grid gap-3">
                    <input className={cx(inputClass, "bg-white")} value={formData.models.vlModel} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, vlModel: event.target.value } }))} placeholder="模型名" />
                    <SecretInput value={formData.models.vlApiKey} onChange={(value) => updateDraft((current) => ({ ...current, models: { ...current.models, vlApiKey: value } }))} />
                    <input className={cx(inputClass, "bg-white")} value={formData.models.vlBaseUrl} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, vlBaseUrl: event.target.value } }))} placeholder="基础地址" />
                  </div>
                </Field>
              </SectionCard>
            );
          default:
            return null;
        }
      case "channels":
        switch (currentSubsectionId) {
          case "telegram":
            return (
              <SectionCard>
                <Field label="Telegram Token">
                  <SecretInput value={draft.channels.telegramToken} onChange={(value) => updateDraft((current) => ({ ...current, channels: { ...current.channels, telegramToken: value } }))} />
                </Field>
                <Field label="Telegram Allow From" hint="每行一个用户名，不带 @。">
                  <textarea className={cx(textareaClass, "min-h-20 bg-white")} value={joinLines(draft.channels.telegramAllowFrom)} onChange={(event) => updateDraft((current) => ({ ...current, channels: { ...current.channels, telegramAllowFrom: splitLines(event.target.value) } }))} />
                </Field>
                <Field label="Telegram Channel Name">
                  <input className={cx(inputClass, "bg-white")} value={draft.channels.telegramChannelName} onChange={(event) => updateDraft((current) => ({ ...current, channels: { ...current.channels, telegramChannelName: event.target.value } }))} />
                </Field>
                {renderRoleBindingsForChannel("telegram")}
              </SectionCard>
            );
          case "qq":
            return (
              <SectionCard>
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
                {renderRoleBindingsForChannel("qq")}
              </SectionCard>
            );
          case "qqbot":
            return (
              <SectionCard>
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
                {renderRoleBindingsForChannel("qqbot")}
              </SectionCard>
            );
          case "feishu":
            return (
              <SectionCard>
                <Field label="Feishu App ID">
                  <input className={cx(inputClass, "bg-white")} value={draft.channels.feishuAppId} onChange={(event) => updateDraft((current) => ({ ...current, channels: { ...current.channels, feishuAppId: event.target.value } }))} />
                </Field>
                <Field label="Feishu App Secret">
                  <SecretInput value={draft.channels.feishuAppSecret} onChange={(value) => updateDraft((current) => ({ ...current, channels: { ...current.channels, feishuAppSecret: value } }))} />
                </Field>
                <Field label="Feishu Allow From" hint="每行一个 open_id / user_id / union_id；留空表示允许所有人。">
                  <textarea className={cx(textareaClass, "min-h-20 bg-white")} value={joinLines(draft.channels.feishuAllowFrom)} onChange={(event) => updateDraft((current) => ({ ...current, channels: { ...current.channels, feishuAllowFrom: splitLines(event.target.value) } }))} />
                </Field>
                <Field label="Feishu Domain" hint="默认 open.feishu.cn；Lark 或私有化部署时再改。">
                  <input className={cx(inputClass, "bg-white")} value={draft.channels.feishuDomain} onChange={(event) => updateDraft((current) => ({ ...current, channels: { ...current.channels, feishuDomain: event.target.value } }))} />
                </Field>
                {renderRoleBindingsForChannel("feishu")}
              </SectionCard>
            );
          case "cli":
            return (
              <SectionCard>
                <Field label="CLI Socket">
                  <input className={cx(inputClass, "bg-white")} value={draft.channels.cliSocket} onChange={(event) => updateDraft((current) => ({ ...current, channels: { ...current.channels, cliSocket: event.target.value } }))} />
                </Field>
                <Field label="CLI Session Key">
                  <input className={cx(inputClass, "bg-white")} value={draft.channels.cliSessionKey} onChange={(event) => updateDraft((current) => ({ ...current, channels: { ...current.channels, cliSessionKey: event.target.value } }))} />
                </Field>
                {renderRoleBindingsForChannel("cli")}
              </SectionCard>
            );
          default:
            return null;
        }
      case "memory":
        switch (currentSubsectionId) {
          case "general":
            return (
              <SectionCard>
                <Field label="启用记忆">
                  <label className="flex items-center gap-3 rounded-xl border border-[#E6E9EE] bg-[#FBFBFC] px-4 py-3">
                    <input type="checkbox" checked={draft.memory.enabled} onChange={(event) => updateDraft((current) => ({ ...current, memory: { ...current.memory, enabled: event.target.checked } }))} />
                    <span>memory.enabled</span>
                  </label>
                </Field>
                <Field label="记忆引擎" hint="default 对应 default_memory 插件。">
                  <select className={cx(inputClass, "bg-white")} value={draft.memory.engine} onChange={(event) => updateDraft((current) => ({ ...current, memory: { ...current.memory, engine: event.target.value } }))}>
                    {getMemoryEngineOptions(draft.memory.engine).map((option) => (
                      <option key={option.value || "default"} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                </Field>
              </SectionCard>
            );
          case "embedding":
            return (
              <SectionCard>
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
            );
          default:
            return null;
        }
      case "proactive":
        switch (currentSubsectionId) {
          case "general":
            return (
              <SectionCard>
                <Field label="启用主动推送">
                  <label className="flex items-center gap-3 rounded-xl border border-[#E6E9EE] bg-[#FBFBFC] px-4 py-3">
                    <input type="checkbox" checked={draft.proactive.enabled} onChange={(event) => updateDraft((current) => ({ ...current, proactive: { ...current.proactive, enabled: event.target.checked } }))} />
                    <span>proactive.enabled</span>
                  </label>
                </Field>
                <Field label="配置档">
                  <input className={cx(inputClass, "bg-white")} value={draft.proactive.profile} onChange={(event) => updateDraft((current) => ({ ...current, proactive: { ...current.proactive, profile: event.target.value } }))} />
                </Field>
                <Field label="高级策略说明" hint="`proactive.profile` 是当前启用的策略名。像 `proactive.profiles`、`proactive.overrides` 这类高级策略树，继续放到高级 TOML 区编辑更稳妥。">
                  <div className="rounded-2xl border border-[#E7EAF0] bg-[#FBFBFC] px-4 py-3 text-sm leading-6 text-[#5B616A]">
                    常用运行项在这里改；复杂策略预设、覆盖白名单和实验参数，放在下方“高级”页的 TOML 文本区维护。
                  </div>
                </Field>
              </SectionCard>
            );
          case "target":
            return (
              <SectionCard>
                <Field label="目标频道与 Chat ID">
                  <div className="grid gap-3 md:grid-cols-2">
                    <input className={cx(inputClass, "bg-white")} value={draft.proactive.targetChannel} onChange={(event) => updateDraft((current) => ({ ...current, proactive: { ...current.proactive, targetChannel: event.target.value } }))} placeholder="频道名" />
                    <input className={cx(inputClass, "bg-white")} value={draft.proactive.targetChatId} onChange={(event) => updateDraft((current) => ({ ...current, proactive: { ...current.proactive, targetChatId: event.target.value } }))} placeholder="会话 ID" />
                  </div>
                </Field>
                <Field label="默认角色" hint="主动推送优先使用这个角色；如果该角色绑定了多个 transport，仍建议同时明确填写目标频道和 Chat ID。">
                  <select className={cx(inputClass, "bg-white")} value={draft.proactive.targetRoleId} onChange={(event) => updateDraft((current) => ({ ...current, proactive: { ...current.proactive, targetRoleId: event.target.value } }))}>
                    <option value="">不指定</option>
                    {roles.map((role) => (
                      <option key={role.id} value={role.id}>{role.name}</option>
                    ))}
                  </select>
                </Field>
              </SectionCard>
            );
          case "agent":
            return (
              <SectionCard>
                <Field label="Proactive 模型" hint="专用于主动推送 / agent tick；留空表示继续使用默认回退路径。">
                  <div className="grid gap-3">
                    <input className={cx(inputClass, "bg-white")} value={draft.models.agentModel} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, agentModel: event.target.value } }))} placeholder="模型名" />
                    <SecretInput value={draft.models.agentApiKey} onChange={(value) => updateDraft((current) => ({ ...current, models: { ...current.models, agentApiKey: value } }))} />
                    <input className={cx(inputClass, "bg-white")} value={draft.models.agentBaseUrl} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, agentBaseUrl: event.target.value } }))} placeholder="基础地址" />
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
              </SectionCard>
            );
          case "drift":
            return (
              <SectionCard>
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
            );
          default:
            return null;
        }
      case "integrations":
        switch (currentSubsectionId) {
          case "novelai":
            return (
              <SectionCard>
                <Field label="NovelAI / 生图">
                  <div className="grid gap-3">
                    <label className="flex items-center gap-3 rounded-xl border border-[#E6E9EE] bg-[#FBFBFC] px-4 py-3">
                      <input type="checkbox" checked={draft.integrations.novelaiEnabled} onChange={(event) => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, novelaiEnabled: event.target.checked } }))} />
                      <span>integrations.novelai.enabled</span>
                    </label>
                    <SecretInput value={draft.integrations.novelaiToken} onChange={(value) => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, novelaiToken: value } }))} />
                    <input className={cx(inputClass, "bg-white")} value={draft.integrations.novelaiBaseUrl} onChange={(event) => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, novelaiBaseUrl: event.target.value } }))} placeholder="Base URL" />
                    <input className={cx(inputClass, "bg-white")} value={draft.integrations.novelaiDefaultModel} onChange={(event) => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, novelaiDefaultModel: event.target.value } }))} placeholder="默认模型" />
                    <div className="grid gap-3 md:grid-cols-2">
                      <label className="flex items-center gap-3 rounded-xl border border-[#E6E9EE] bg-[#FBFBFC] px-4 py-3">
                        <input type="checkbox" checked={draft.integrations.novelaiAllowTxt2img} onChange={(event) => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, novelaiAllowTxt2img: event.target.checked } }))} />
                        <span>允许文生图</span>
                      </label>
                      <label className="flex items-center gap-3 rounded-xl border border-[#E6E9EE] bg-[#FBFBFC] px-4 py-3">
                        <input type="checkbox" checked={draft.integrations.novelaiAllowImg2img} onChange={(event) => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, novelaiAllowImg2img: event.target.checked } }))} />
                        <span>允许图生图</span>
                      </label>
                      <label className="flex items-center gap-3 rounded-xl border border-[#E6E9EE] bg-[#FBFBFC] px-4 py-3 md:col-span-2">
                        <input type="checkbox" checked={draft.integrations.novelaiAutoWritebackRoleAssets} onChange={(event) => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, novelaiAutoWritebackRoleAssets: event.target.checked } }))} />
                        <span>生成后自动写回角色素材</span>
                      </label>
                    </div>
                    <div className="grid gap-3 md:grid-cols-2">
                      <input className={cx(inputClass, "bg-white")} value={String(draft.integrations.novelaiMaxSteps)} onChange={(event) => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, novelaiMaxSteps: parseNumber(event.target.value, current.integrations.novelaiMaxSteps) } }))} placeholder="最大步数" />
                      <input className={cx(inputClass, "bg-white")} value={String(draft.integrations.novelaiMaxPixels)} onChange={(event) => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, novelaiMaxPixels: parseNumber(event.target.value, current.integrations.novelaiMaxPixels) } }))} placeholder="最大总像素" />
                    </div>
                  </div>
                </Field>
              </SectionCard>
            );
          case "fitbit":
            return (
              <SectionCard>
                <Field label="Fitbit">
                  <label className="flex items-center gap-3 rounded-xl border border-[#E6E9EE] bg-[#FBFBFC] px-4 py-3">
                    <input type="checkbox" checked={draft.integrations.fitbitEnabled} onChange={(event) => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, fitbitEnabled: event.target.checked } }))} />
                    <span>integrations.fitbit.enabled</span>
                  </label>
                </Field>
              </SectionCard>
            );
          case "peer-agents":
            return (
              <SectionCard>
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
            );
          default:
            return null;
        }
      case "advanced":
        switch (currentSubsectionId) {
          case "general":
            return (
              <SectionCard>
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
              </SectionCard>
            );
          case "wiring":
            return (
              <SectionCard>
                <Field label="Wiring">
                  <div className="grid gap-3">
                    <input className={cx(inputClass, "bg-white")} value={draft.advanced.wiringContext} onChange={(event) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, wiringContext: event.target.value } }))} placeholder="上下文实现名" />
                    <input className={cx(inputClass, "bg-white")} value={draft.advanced.wiringMemory} onChange={(event) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, wiringMemory: event.target.value } }))} placeholder="记忆实现名" />
                    <textarea className={cx(textareaClass, "min-h-20 bg-white")} value={joinLines(draft.advanced.wiringToolsets)} onChange={(event) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, wiringToolsets: splitLines(event.target.value) } }))} placeholder="每行一个工具集名称" />
                  </div>
                </Field>
              </SectionCard>
            );
          case "plugins":
            return (
              <SectionCard>
                <Field label="其他插件配置" hint="保留给尚未表单化的 plugins.* 段，以及主动推送的高级策略项。按 TOML 片段填写。">
                  <textarea className={cx(textareaClass, "min-h-[240px] bg-white font-mono text-[12px]")} value={draft.advanced.pluginsRawToml} onChange={(event) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, pluginsRawToml: event.target.value } }))} />
                </Field>
                <Field label="TOML 提示" hint="这里最适合放表单之外、但仍然需要保留的高级配置。">
                  <div className="rounded-2xl border border-[#E7EAF0] bg-[#FBFBFC] px-4 py-3 text-sm leading-6 text-[#5B616A]">
                    例如：`proactive.profiles`、`proactive.overrides`、尚未表单化的 `plugins.*` 配置。这里填写的是原始 TOML 片段，会原样写回配置文件。
                  </div>
                </Field>
              </SectionCard>
            );
          default:
            return null;
        }
      default:
        return null;
    }
  }

  return (
    <section className="settings-page relative grid h-full grid-rows-[auto_minmax(0,1fr)] overflow-hidden bg-[#F7F8FB]" data-testid="settings-page">
      {(savePhase === "saved" || savePhase === "restart-failed" || savePhase === "error") && statusMessage ? (
        <div
          className={cx(
            "pointer-events-none absolute left-1/2 top-4 z-20 max-w-[560px] -translate-x-1/2 rounded-[14px] border px-4 py-2.5 text-sm leading-6 shadow-[0_16px_40px_rgba(15,23,42,0.12)] backdrop-blur-[8px]",
            savePhase === "saved"
              ? "border-[rgba(26,106,58,0.18)] bg-[rgba(237,248,240,0.94)] text-[#1a6a3a]"
              : "border-[rgba(176,58,58,0.18)] bg-[rgba(255,241,241,0.96)] text-[#9a2f2f]",
          )}
          role="status"
          aria-live="polite"
        >
          {statusMessage}
        </div>
      ) : null}
      <div className="settings-content grid min-h-0 grid-rows-[auto_minmax(0,1fr)] overflow-hidden">
        <div className="border-b border-[#E8EBF0] bg-[#F7F8FB] px-10 py-5">
          <div className="mx-auto flex w-full max-w-[940px] items-center gap-4">
            <div className="min-w-0 flex-1">
              {visibleSubsections.length ? (
                <div className="relative max-w-[260px]">
                  <select
                    className="h-10 w-full appearance-none rounded-md border border-[#D8DCE2] bg-white px-3.5 pr-10 text-sm leading-5 text-[#1f1f1f] transition focus:border-[#D8DCE2] focus:outline-none focus:ring-0 focus-visible:border-[#D8DCE2] focus-visible:outline-none focus-visible:ring-0"
                    value={currentSubsectionId ?? ""}
                    onChange={(event) => updateActiveSubsection(event.target.value)}
                  >
                    {visibleSubsections.map((item) => (
                      <option key={item.id} value={item.id}>{item.label}</option>
                    ))}
                  </select>
                  <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-[#737781]" aria-hidden="true">
                    <svg viewBox="0 0 12 12" className="h-3.5 w-3.5 fill-current">
                      <path d="M2.2 4.2 6 8l3.8-3.8.8.8L6 9.8 1.4 5z" />
                    </svg>
                  </span>
                </div>
              ) : null}
            </div>
            <div className="flex items-center gap-2.5">
              <button
                className={cx(floatingActionClass, "border-black/8 text-[#747474] hover:border-black/14 hover:bg-[#F5F7FA] hover:text-[#4f4f4f]")}
                type="button"
                aria-label="重置"
                onClick={reset}
                disabled={!isDirty}
              >
                  <ResetIcon className="h-[18px] w-[18px] fill-current" />
              </button>
              <button
                className={cx(floatingActionClass, "border-transparent bg-white text-[#1f1f1f] hover:bg-[#F5F7FA]")}
                type="button"
                aria-label="保存并重启"
                onClick={() => void save()}
                disabled={!bridgeReady || !isDirty || savePhase === "saving"}
              >
                  <SaveIcon className="h-[18px] w-[18px] fill-current" />
              </button>
            </div>
          </div>
        </div>
        <div className="relative scrollbar-soft overflow-y-auto px-10 py-8">
          <div className="mx-auto w-full max-w-[940px]">
            {!currentSection ? (
              <div className={cx(cardClass, "grid min-h-[240px] place-items-center border-dashed text-sm text-[#7f8490]")}>
                没有匹配的设置项
              </div>
            ) : null}
            {currentSection ? renderCurrentSectionContent() : null}
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

function ChannelRoleBindingEditor({
  channel,
  binding,
  roles,
  onChange,
  onRemove,
}: {
  channel: SettingsChannelRoleBinding["channel"];
  binding: SettingsChannelRoleBinding;
  roles: RoleRecord[];
  onChange: (next: SettingsChannelRoleBinding) => void;
  onRemove: () => void;
}) {
  const chatIdMeta = getBindingChatIdMeta(channel);

  return (
    <div className="grid gap-3 rounded-2xl border border-[#E7EAF0] bg-[#FBFBFC] p-4">
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium text-[#20242A]">渠道角色绑定</div>
        <button className="text-sm text-[#A14D32]" type="button" onClick={onRemove}>删除</button>
      </div>
      <input className={cx(inputClass, "bg-white")} value={binding.chatId} onChange={(event) => onChange({ ...binding, channel, chatId: event.target.value })} placeholder={chatIdMeta.placeholder} />
      <div className="grid gap-1">
        <div className="text-xs font-medium text-[#4A4F57]">{chatIdMeta.label}</div>
        <div className="text-[12px] leading-5 text-[#7B7F87]">{chatIdMeta.hint}</div>
      </div>
      <select className={cx(inputClass, "bg-white")} value={binding.roleId} onChange={(event) => onChange({ ...binding, channel, roleId: event.target.value })}>
        <option value="">选择角色</option>
        {roles.map((role) => (
          <option key={role.id} value={role.id}>{role.name}</option>
        ))}
      </select>
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
