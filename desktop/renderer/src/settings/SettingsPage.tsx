import type React from "react";
import { useDeferredValue, useEffect, useState } from "react";
import { type SettingsSectionId, settingsSections } from "./SettingsSidebar";
import { SettingsToggleCard } from "./SettingsToggleCard";
import {
  cardClass,
  cx,
  ghostButtonClass,
  inputClass,
  textareaClass,
} from "../shared/styles";
import { DeleteIcon, PlusIcon, ResetIcon, SaveIcon } from "../shared/icons";
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

type ProactiveTargetOption = {
  value: string;
  label: string;
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

function hydrateSettingsSnapshot(snapshot: SettingsSnapshot, roleBindings: SettingsChannelRoleBinding[]): SettingsSnapshot {
  const nextFormData = cloneSettings(snapshot.formData);
  nextFormData.channels.roleBindings = roleBindings;
  return {
    ...snapshot,
    formData: nextFormData,
  };
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
    case "desktop":
      return {
        label: "Desktop Session",
        placeholder: "自动使用 role:<role_id>",
        hint: "桌面端会把主动消息直接写入该角色会话，不需要手填 chat_id。",
      };
    case "telegram":
      return {
        label: "Telegram Chat ID",
        placeholder: "例如 123456789", 
        hint: "",
      };
    case "qq":
      return {
        label: "QQ Chat ID",
        placeholder: "例如好友 QQ 号或群号",
        hint: "",
      };
    case "qqbot":
      return {
        label: "QQBot Chat ID",
        placeholder: "例如 c2c:USER_OPENID",
        hint: "",
      };
    case "feishu":
      return {
        label: "Feishu Chat ID",
        placeholder: "例如 open_id / chat_id",
        hint: "",
      };
    case "cli":
      return {
        label: "CLI Session Key",
        placeholder: "例如 local 或 cli:local",
        hint: "",
      };
    default:
      return {
        label: "Chat ID",
        placeholder: "输入 transport chat_id",
        hint: "填入该渠道实际使用的 chat_id。",
      };
  }
}

const proactiveTargetOptions: ProactiveTargetOption[] = [
  { value: "desktop", label: "桌面端" },
  { value: "telegram", label: "Telegram" },
  { value: "qq", label: "QQ" },
  { value: "qqbot", label: "QQBot" },
  { value: "feishu", label: "Feishu" },
  { value: "cli", label: "CLI" },
];

const proactiveProfileOptions: Array<{ value: string; label: string }> = [
  { value: "daily", label: "daily" },
];

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
  layout = "side",
  children,
}: {
  label: string;
  hint?: string;
  layout?: "side" | "stack";
  children: React.ReactNode;
}) {
  const stacked = layout === "stack";
  return (
    <div className={cx(
      "grid gap-3 border-b border-[#ECEEF2] py-5 last:border-b-0",
      stacked
        ? "grid-cols-[minmax(0,1fr)]"
        : "xl:grid-cols-[minmax(0,1fr)_minmax(240px,360px)] xl:items-start xl:gap-8",
    )}>
      <div className="grid gap-1.5">
        <div className="text-[15px] font-medium text-[#171717]">{label}</div>
        {hint ? <div className="max-w-[680px] text-[13px] leading-6 text-[#7B7F87]">{hint}</div> : null}
      </div>
      <div className={cx("w-full", !stacked && "xl:justify-self-end")}>{children}</div>
    </div>
  );
}

function ToggleField({
  label,
  hint,
  checked,
  disabled,
  onChange,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <Field label={label} hint={hint}>
      <div className="flex w-full justify-end">
        <SettingsToggleCard
          checked={checked}
          disabled={disabled}
          ariaLabel={label}
          onChange={onChange}
        />
      </div>
    </Field>
  );
}

function CompactToggleField({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border border-[#E6E9EE] bg-white px-3.5 py-3">
      <span className="text-sm font-medium text-[#20242A]">{label}</span>
      <SettingsToggleCard compact checked={checked} ariaLabel={label} onChange={onChange} />
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
  return <section className="grid">{children}</section>;
}

function EditorCard({
  title,
  onRemove,
  children,
}: {
  title: string;
  onRemove: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="grid gap-3 rounded-[22px] bg-[#FBFBFC] px-2 py-1">
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm font-medium text-[#20242A]">{title}</div>
        <button
          className="grid h-8 w-8 place-items-center rounded-full border border-transparent text-[#C16E4E] transition hover:bg-white focus:outline-none focus:ring-2 focus:ring-primary/20"
          type="button"
          aria-label={`删除${title}`}
          onClick={onRemove}
        >
          <DeleteIcon className="h-[14px] w-[14px] fill-current" />
        </button>
      </div>
      {children}
    </div>
  );
}

function AddListAction({
  label,
  onAdd,
}: {
  label: string;
  onAdd: () => void;
}) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-full bg-[#FFF9F0] px-5 py-3">
      <span className="text-sm text-[#6B5A45]">{label}</span>
      <button
        className="grid h-11 w-11 place-items-center rounded-full bg-white text-[#6B5A45] transition hover:bg-[#FFFCF7] focus:outline-none focus:ring-2 focus:ring-primary/20"
        type="button"
        aria-label={label}
        onClick={onAdd}
      >
        <PlusIcon className="h-[18px] w-[18px] fill-current" />
      </button>
    </div>
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
  const desktopTargetRoleId = draft?.proactive.targetRoleId.trim() ?? "";
  const desktopTargetChatId = desktopTargetRoleId ? `role:${desktopTargetRoleId}` : "";
  const proactiveTargetMeta = getBindingChatIdMeta(draft?.proactive.targetChannel ?? "");

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
        const hydratedSnapshot = hydrateSettingsSnapshot(nextSnapshot, nextBindings.bindings);
        if (rolesResponse.error) {
          throw new Error(rolesResponse.error.message);
        }
        setSnapshot(hydratedSnapshot);
        setDraft(cloneSettings(hydratedSnapshot.formData));
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

  function updateProactiveTargetChannel(nextChannel: string): void {
    setDraft((current) => {
      if (!current) return current;
      const currentRoleId = current.proactive.targetRoleId.trim();
      const currentDesktopChatId = currentRoleId ? `role:${currentRoleId}` : "";
      const currentChatId = current.proactive.targetChatId;
      const nextChatId = nextChannel === "desktop"
        ? currentDesktopChatId
        : (current.proactive.targetChannel === "desktop" && currentChatId === currentDesktopChatId ? "" : currentChatId);
      return {
        ...current,
        proactive: {
          ...current.proactive,
          targetChannel: nextChannel,
          targetChatId: nextChatId,
        },
      };
    });
  }

  function updateProactiveTargetRoleId(nextRoleId: string): void {
    setDraft((current) => {
      if (!current) return current;
      return {
        ...current,
        proactive: {
          ...current.proactive,
          targetRoleId: nextRoleId,
          targetChatId: current.proactive.targetChannel === "desktop" && nextRoleId.trim()
            ? `role:${nextRoleId.trim()}`
            : current.proactive.targetChannel === "desktop"
              ? ""
              : current.proactive.targetChatId,
        },
      };
    });
  }

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
      const hydratedSnapshot = hydrateSettingsSnapshot(nextSnapshot, nextBindings.bindings);
      setSnapshot(hydratedSnapshot);
      setDraft(cloneSettings(hydratedSnapshot.formData));
    } catch (error) {
      setSavePhase("error");
      setStatusMessage(error instanceof Error ? error.message : String(error));
    }
  }

  function reset(): void {
    if (!snapshot) return;
    setDraft(cloneSettings(snapshot.formData));
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
        <Field label="角色绑定" hint="把当前频道里的具体会话身份绑定到角色。" layout="stack">
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
            )) : null}
            <AddListAction label="添加角色绑定" onAdd={() => updateDraft((current) => ({
              ...current,
              channels: {
                ...current.channels,
                roleBindings: [...current.channels.roleBindings, { channel, chatId: "", roleId: "" }],
              },
            }))} />
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
                <Field label="主模型" hint="对话使用的模型。">
                  <input className={cx(inputClass, "bg-white")} value={formData.models.mainModel} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, mainModel: event.target.value } }))} />
                </Field>
                <Field label="API Key">
                  <SecretInput value={formData.models.mainApiKey} onChange={(value) => updateDraft((current) => ({ ...current, models: { ...current.models, mainApiKey: value } }))} />
                </Field>
                <Field label="Base URL">
                  <input className={cx(inputClass, "bg-white")} value={formData.models.mainBaseUrl} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, mainBaseUrl: event.target.value } }))} />
                </Field>
                <Field label="Reasoning Effort" hint="支持的模型可用，用于控制推理强度；留空表示不写入。">
                  <input className={cx(inputClass, "bg-white")} value={formData.models.reasoningEffort} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, reasoningEffort: event.target.value } }))} placeholder="例如 low / medium / high" />
                </Field>
                <ToggleField label="启用 Thinking" checked={formData.models.enableThinking} onChange={(checked) => updateDraft((current) => ({ ...current, models: { ...current.models, enableThinking: checked } }))} />
                <ToggleField label="启用多模态" checked={formData.models.multimodal} onChange={(checked) => updateDraft((current) => ({ ...current, models: { ...current.models, multimodal: checked } }))} />
              </SectionCard>
            );
          case "fast":
            return (
              <SectionCard>
                <Field label="轻量模型" hint="轻量任务时使用的模型名；留空时则沿用主模型。">
                  <input className={cx(inputClass, "bg-white")} value={formData.models.fastModel} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, fastModel: event.target.value } }))} placeholder="模型名" />
                </Field>
                <Field label="API Key">
                  <SecretInput value={formData.models.fastApiKey} onChange={(value) => updateDraft((current) => ({ ...current, models: { ...current.models, fastApiKey: value } }))} />
                </Field>
                <Field label="Base URL">
                  <input className={cx(inputClass, "bg-white")} value={formData.models.fastBaseUrl} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, fastBaseUrl: event.target.value } }))} placeholder="基础地址" />
                </Field>
              </SectionCard>
            );
          case "vl":
            return (
              <SectionCard>
                <Field label="视觉模型" hint="若主模型未启动多模态，则使用该模型；留空时则沿用主模型。">
                  <input className={cx(inputClass, "bg-white")} value={formData.models.vlModel} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, vlModel: event.target.value } }))} placeholder="模型名" />
                </Field>
                <Field label="API Key" hint="">
                  <SecretInput value={formData.models.vlApiKey} onChange={(value) => updateDraft((current) => ({ ...current, models: { ...current.models, vlApiKey: value } }))} />
                </Field>
                <Field label="Base URL" hint="">
                  <input className={cx(inputClass, "bg-white")} value={formData.models.vlBaseUrl} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, vlBaseUrl: event.target.value } }))} placeholder="基础地址" />
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
                {renderRoleBindingsForChannel("telegram")}
              </SectionCard>
            );
          case "qq":
            return (
              <SectionCard>
                <Field label="Bot QQ号" hint="填入Bot 的QQ号；留空则不启用 QQ 渠道。">
                  <input className={cx(inputClass, "bg-white")} value={draft.channels.qqBotUin} onChange={(event) => updateDraft((current) => ({ ...current, channels: { ...current.channels, qqBotUin: event.target.value } }))} />
                </Field>
                <Field label="QQ Allow From" hint="每行一个 QQ 号。">
                  <textarea className={cx(textareaClass, "min-h-20 bg-white")} value={joinLines(draft.channels.qqAllowFrom)} onChange={(event) => updateDraft((current) => ({ ...current, channels: { ...current.channels, qqAllowFrom: splitLines(event.target.value) } }))} />
                </Field>
                <Field label="QQ 群组规则" layout="stack">
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
                    <AddListAction label="添加 QQ 群组" onAdd={() => updateDraft((current) => ({
                      ...current,
                      channels: {
                        ...current.channels,
                        qqGroups: [...current.channels.qqGroups, { groupId: "", allowFrom: [], requireAt: true }],
                      },
                    }))} />
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
                <Field label="QQBot 群组规则" layout="stack">
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
                    <AddListAction label="添加 QQBot 群组" onAdd={() => updateDraft((current) => ({
                      ...current,
                      channels: {
                        ...current.channels,
                        qqbotGroups: [...current.channels.qqbotGroups, { groupOpenid: "", allowFrom: [], requireAt: true, allowProactive: false }],
                      },
                    }))} />
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
                {renderRoleBindingsForChannel("feishu")}
              </SectionCard>
            );
          case "cli":
            return (
              <SectionCard>
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
                <ToggleField label="启用记忆" checked={draft.memory.enabled} onChange={(checked) => updateDraft((current) => ({ ...current, memory: { ...current.memory, enabled: checked } }))} />
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
                <Field label="API Key">
                  <SecretInput value={draft.memory.embeddingApiKey} onChange={(value) => updateDraft((current) => ({ ...current, memory: { ...current.memory, embeddingApiKey: value } }))} />
                </Field>
                <Field label="Base URL">
                  <input className={cx(inputClass, "bg-white")} value={draft.memory.embeddingBaseUrl} onChange={(event) => updateDraft((current) => ({ ...current, memory: { ...current.memory, embeddingBaseUrl: event.target.value } }))} />
                </Field>
                <Field label="输出维度">
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
                <ToggleField label="主动推送" checked={draft.proactive.enabled} onChange={(checked) => updateDraft((current) => ({ ...current, proactive: { ...current.proactive, enabled: checked } }))} />
                <Field label="推送策略" hint="当前设置页先开放内置的 `daily` 策略。">
                  <select className={cx(inputClass, "bg-white")} value={draft.proactive.profile} onChange={(event) => updateDraft((current) => ({ ...current, proactive: { ...current.proactive, profile: event.target.value } }))}>
                    {proactiveProfileOptions.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                </Field>
              </SectionCard>
            );
          case "target":
            return (
              <SectionCard>
                <Field label="目标">
                  <select className={cx(inputClass, "bg-white")} value={draft.proactive.targetChannel} onChange={(event) => updateProactiveTargetChannel(event.target.value)}>
                    <option value="">请选择目标</option>
                    {proactiveTargetOptions.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                </Field>
                <Field label="默认角色" hint="主动推送优先使用这个角色；如果该角色绑定了多个 transport，仍建议同时明确填写目标频道和 Chat ID。">
                  <select className={cx(inputClass, "bg-white")} value={draft.proactive.targetRoleId} onChange={(event) => updateProactiveTargetRoleId(event.target.value)}>
                    <option value="" disabled={draft.proactive.enabled}>请选择角色</option>
                    {roles.map((role) => (
                      <option key={role.id} value={role.id}>{role.name}</option>
                    ))}
                  </select>
                </Field>
                {draft.proactive.targetChannel ? (
                  <Field label={proactiveTargetMeta.label} hint={proactiveTargetMeta.hint}>
                    {draft.proactive.targetChannel === "desktop" ? (
                      <input className={cx(inputClass, "bg-[#F6F7F9] text-[#6D737D]")} value={desktopTargetChatId} readOnly placeholder={proactiveTargetMeta.placeholder} />
                    ) : (
                      <input className={cx(inputClass, "bg-white")} value={draft.proactive.targetChatId} onChange={(event) => updateDraft((current) => current ? ({ ...current, proactive: { ...current.proactive, targetChatId: event.target.value } }) : current)} placeholder={proactiveTargetMeta.placeholder} />
                    )}
                  </Field>
                ) : null}
              </SectionCard>
            );
          case "agent":
            return (
              <SectionCard>
                <Field label="model" hint="专用于主动推送 / agent tick；留空时回退到主模型。">
                  <input className={cx(inputClass, "bg-white")} value={draft.models.agentModel} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, agentModel: event.target.value } }))} placeholder="模型名" />
                </Field>
                <Field label="api_key" hint="Proactive 专用模型的 API Key。">
                  <SecretInput value={draft.models.agentApiKey} onChange={(value) => updateDraft((current) => ({ ...current, models: { ...current.models, agentApiKey: value } }))} />
                </Field>
                <Field label="base_url" hint="Proactive 专用模型的基础地址。">
                  <input className={cx(inputClass, "bg-white")} value={draft.models.agentBaseUrl} onChange={(event) => updateDraft((current) => ({ ...current, models: { ...current.models, agentBaseUrl: event.target.value } }))} placeholder="基础地址" />
                </Field>
                <Field label="max_steps" hint="限制单次主动推送任务可执行的最大步数。">
                  <input className={cx(inputClass, "bg-white")} value={String(draft.proactive.agentMaxSteps)} onChange={(event) => updateDraft((current) => ({ ...current, proactive: { ...current.proactive, agentMaxSteps: parseNumber(event.target.value, current.proactive.agentMaxSteps) } }))} placeholder="最大步数" />
                </Field>
                <Field label="content_limit" hint="限制单次主动推送可选取的内容条目数量。">
                  <input className={cx(inputClass, "bg-white")} value={String(draft.proactive.agentContentLimit)} onChange={(event) => updateDraft((current) => ({ ...current, proactive: { ...current.proactive, agentContentLimit: parseNumber(event.target.value, current.proactive.agentContentLimit) } }))} placeholder="内容长度限制" />
                </Field>
                <Field label="web_fetch_max_chars" hint="限制网页抓取后允许注入上下文的最大字符数。">
                  <input className={cx(inputClass, "bg-white")} value={String(draft.proactive.agentWebFetchMaxChars)} onChange={(event) => updateDraft((current) => ({ ...current, proactive: { ...current.proactive, agentWebFetchMaxChars: parseNumber(event.target.value, current.proactive.agentWebFetchMaxChars) } }))} placeholder="网页抓取最大字符数" />
                </Field>
                <Field label="context_prob" hint="控制主动推送优先走上下文型内容的概率。">
                  <input className={cx(inputClass, "bg-white")} value={String(draft.proactive.agentContextProb)} onChange={(event) => updateDraft((current) => ({ ...current, proactive: { ...current.proactive, agentContextProb: parseNumber(event.target.value, current.proactive.agentContextProb) } }))} placeholder="上下文概率" />
                </Field>
                <Field label="delivery_cooldown_hours" hint="限制两次主动推送之间的最小冷却小时数。">
                  <input className={cx(inputClass, "bg-white")} value={String(draft.proactive.agentDeliveryCooldownHours)} onChange={(event) => updateDraft((current) => ({ ...current, proactive: { ...current.proactive, agentDeliveryCooldownHours: parseNumber(event.target.value, current.proactive.agentDeliveryCooldownHours) } }))} placeholder="发送冷却小时数" />
                </Field>
              </SectionCard>
            );
          case "drift":
            return (
              <SectionCard>
                <ToggleField label="启用 Drift" checked={draft.proactive.driftEnabled} onChange={(checked) => updateDraft((current) => ({ ...current, proactive: { ...current.proactive, driftEnabled: checked } }))} />
                <Field label="max_steps" hint="限制 Drift 单次自主任务的最大步数。">
                  <input className={cx(inputClass, "bg-white")} value={String(draft.proactive.driftMaxSteps)} onChange={(event) => updateDraft((current) => ({ ...current, proactive: { ...current.proactive, driftMaxSteps: parseNumber(event.target.value, current.proactive.driftMaxSteps) } }))} placeholder="最大步数" />
                </Field>
                <Field label="min_interval_hours" hint="限制两次 Drift 任务之间的最小间隔小时数。">
                  <input className={cx(inputClass, "bg-white")} value={String(draft.proactive.driftMinIntervalHours)} onChange={(event) => updateDraft((current) => ({ ...current, proactive: { ...current.proactive, driftMinIntervalHours: parseNumber(event.target.value, current.proactive.driftMinIntervalHours) } }))} placeholder="最小间隔小时数" />
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
                <ToggleField label="启用 NovelAI" checked={draft.integrations.novelaiEnabled} onChange={(checked) => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, novelaiEnabled: checked } }))} />
                <Field label="Token">
                  <SecretInput value={draft.integrations.novelaiToken} onChange={(value) => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, novelaiToken: value } }))} />
                </Field>
                <ToggleField label="Add Quality Tags" checked={draft.integrations.novelaiAddQualityTags} onChange={(checked) => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, novelaiAddQualityTags: checked } }))} />
                <Field label="内容过滤预设" hint="控制默认 undesired content 强度。">
                  <select
                    className="h-12 w-full rounded-md border border-[#D8DCE2] bg-white px-3.5 text-sm leading-5 text-[#1f1f1f] transition focus:border-[#D8DCE2] focus:outline-none focus:ring-0 focus-visible:border-[#D8DCE2] focus-visible:outline-none focus-visible:ring-0"
                    value={String(draft.integrations.novelaiUndesiredContentPreset)}
                    onChange={(event) => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, novelaiUndesiredContentPreset: parseNumber(event.target.value, current.integrations.novelaiUndesiredContentPreset) } }))}
                  >
                    <option value="0">Undesired Content Preset: None</option>
                    <option value="1">Undesired Content Preset: Light</option>
                    <option value="2">Undesired Content Preset: Heavy</option>
                  </select>
                </Field>
                <ToggleField label="生成后自动写回角色素材" checked={draft.integrations.novelaiAutoWritebackRoleAssets} onChange={(checked) => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, novelaiAutoWritebackRoleAssets: checked } }))} />
                <ToggleField label="NSFW 模式（开启时使用 Full）" checked={draft.integrations.novelaiNsfwEnabled} onChange={(checked) => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, novelaiNsfwEnabled: checked } }))} />
              </SectionCard>
            );
          case "fitbit":
            return (
              <SectionCard>
                <ToggleField
                  label="启用 Fitbit"
                  hint="启用后允许 Agent 接入 Fitbit 健康数据能力，例如睡眠、步数、心率等信息。"
                  checked={draft.integrations.fitbitEnabled}
                  onChange={(checked) => updateDraft((current) => ({ ...current, integrations: { ...current.integrations, fitbitEnabled: checked } }))}
                />
              </SectionCard>
            );
          case "peer-agents":
            return (
              <SectionCard>
                <Field label="Peer Agents" layout="stack">
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
                    <AddListAction label="添加 Peer Agent" onAdd={() => updateDraft((current) => ({
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
                    }))} />
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
                <Field label="System Prompt" hint="全局系统提示词">
                  <textarea className={cx(textareaClass, "min-h-28 bg-white")} value={draft.advanced.systemPrompt} onChange={(event) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, systemPrompt: event.target.value } }))} />
                </Field>
                <Field label="max_tokens" hint="限制单轮响应可使用的最大 token 数。">
                  <input className={cx(inputClass, "bg-white")} value={String(draft.advanced.maxTokens)} onChange={(event) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, maxTokens: parseNumber(event.target.value, current.advanced.maxTokens) } }))} placeholder="最大令牌数" />
                </Field>
                <Field label="max_iterations" hint="限制 Agent 单次任务允许执行的最大迭代次数。">
                  <input className={cx(inputClass, "bg-white")} value={String(draft.advanced.maxIterations)} onChange={(event) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, maxIterations: parseNumber(event.target.value, current.advanced.maxIterations) } }))} placeholder="最大迭代次数" />
                </Field>
                <Field label="memory_window" hint="控制上下文中保留的记忆窗口大小。">
                  <input className={cx(inputClass, "bg-white")} value={String(draft.advanced.memoryWindow)} onChange={(event) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, memoryWindow: parseNumber(event.target.value, current.advanced.memoryWindow) } }))} placeholder="记忆窗口大小" />
                </Field>
                <Field label="memory_optimizer_interval_seconds" hint="设置记忆优化任务的执行间隔，单位为秒。">
                  <input className={cx(inputClass, "bg-white")} value={String(draft.advanced.memoryOptimizerIntervalSeconds)} onChange={(event) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, memoryOptimizerIntervalSeconds: parseNumber(event.target.value, current.advanced.memoryOptimizerIntervalSeconds) } }))} placeholder="记忆优化间隔秒数" />
                </Field>
                <ToggleField label="dev_mode" hint="启用后暴露更偏开发调试的运行行为和输出。" checked={draft.advanced.devMode} onChange={(checked) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, devMode: checked } }))} />
                <ToggleField label="search_enabled" hint="控制 Agent 是否允许使用搜索能力。" checked={draft.advanced.searchEnabled} onChange={(checked) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, searchEnabled: checked } }))} />
                <ToggleField label="spawn_enabled" hint="控制 Agent 是否允许创建子任务或派生执行流程。" checked={draft.advanced.spawnEnabled} onChange={(checked) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, spawnEnabled: checked } }))} />
                <ToggleField label="memory_optimizer_enabled" hint="控制后台记忆优化任务是否启用。" checked={draft.advanced.memoryOptimizerEnabled} onChange={(checked) => updateDraft((current) => ({ ...current, advanced: { ...current.advanced, memoryOptimizerEnabled: checked } }))} />
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
        <div className="border-b border-[#E8EBF0] bg-[#F7F8FB] px-4 py-4 sm:px-6 lg:px-8">
          <div className="mx-auto flex w-full flex-col gap-4 sm:flex-row sm:items-center">
            <div className="min-w-0 flex-1">
              {visibleSubsections.length ? (
                <div className="relative max-w-full sm:max-w-[260px]">
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
        <div className="relative scrollbar-soft overflow-y-auto bg-white px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <div className="mx-auto w-full max-w-none">
            {!currentSection ? (
              <div className={cx(cardClass, "grid min-h-[240px] place-items-center border-dashed text-sm text-[#7f8490]")}>
                没有匹配的设置项
              </div>
            ) : null}
            {currentSection ? (
              <div>
                {renderCurrentSectionContent()}
              </div>
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
    <EditorCard title="QQ 群组" onRemove={onRemove}>
      <div className="grid gap-3">
        <input className={cx(inputClass, "bg-white")} value={group.groupId} onChange={(event) => onChange({ ...group, groupId: event.target.value })} placeholder="群组 ID" />
        <textarea className={cx(textareaClass, "min-h-16 bg-white")} value={joinLines(group.allowFrom)} onChange={(event) => onChange({ ...group, allowFrom: splitLines(event.target.value) })} placeholder="每行一个允许来源" />
        <div className="grid gap-3">
          <CompactToggleField label="require_at" checked={group.requireAt} onChange={(checked) => onChange({ ...group, requireAt: checked })} />
        </div>
      </div>
    </EditorCard>
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
    <EditorCard title="QQBot 群组" onRemove={onRemove}>
      <div className="grid gap-3">
        <input className={cx(inputClass, "bg-white")} value={group.groupOpenid} onChange={(event) => onChange({ ...group, groupOpenid: event.target.value })} placeholder="群组 OpenID" />
        <textarea className={cx(textareaClass, "min-h-16 bg-white")} value={joinLines(group.allowFrom)} onChange={(event) => onChange({ ...group, allowFrom: splitLines(event.target.value) })} placeholder="每行一个允许来源" />
        <div className="grid gap-3 md:grid-cols-2">
          <CompactToggleField label="require_at" checked={group.requireAt} onChange={(checked) => onChange({ ...group, requireAt: checked })} />
          <CompactToggleField label="allow_proactive" checked={group.allowProactive} onChange={(checked) => onChange({ ...group, allowProactive: checked })} />
        </div>
      </div>
    </EditorCard>
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
    <EditorCard title="渠道角色绑定" onRemove={onRemove}>
      <div className="grid gap-3">
        <div className="grid gap-1.5">
          <div className="text-xs font-medium text-[#4A4F57]">{chatIdMeta.label}</div>
          <input className={cx(inputClass, "bg-white")} value={binding.chatId} onChange={(event) => onChange({ ...binding, channel, chatId: event.target.value })} placeholder={chatIdMeta.placeholder} />
          <div className="text-[12px] leading-5 text-[#7B7F87]">{chatIdMeta.hint}</div>
        </div>
        <div className="grid gap-1.5">
          <div className="text-xs font-medium text-[#4A4F57]">角色</div>
          <select className={cx(inputClass, "bg-white")} value={binding.roleId} onChange={(event) => onChange({ ...binding, channel, roleId: event.target.value })}>
            <option value="">选择角色</option>
            {roles.map((role) => (
              <option key={role.id} value={role.id}>{role.name}</option>
            ))}
          </select>
        </div>
      </div>
    </EditorCard>
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
    <EditorCard title="Peer Agent" onRemove={onRemove}>
      <div className="grid gap-3">
        <input className={cx(inputClass, "bg-white")} value={agent.name} onChange={(event) => onChange({ ...agent, name: event.target.value })} placeholder="名称" />
        <input className={cx(inputClass, "bg-white")} value={agent.baseUrl} onChange={(event) => onChange({ ...agent, baseUrl: event.target.value })} placeholder="基础地址" />
        <input className={cx(inputClass, "bg-white")} value={agent.cwd} onChange={(event) => onChange({ ...agent, cwd: event.target.value })} placeholder="工作目录" />
        <input className={cx(inputClass, "bg-white")} value={agent.healthPath} onChange={(event) => onChange({ ...agent, healthPath: event.target.value })} placeholder="健康检查路径" />
        <input className={cx(inputClass, "bg-white")} value={String(agent.startupTimeoutSeconds)} onChange={(event) => onChange({ ...agent, startupTimeoutSeconds: parseNumber(event.target.value, agent.startupTimeoutSeconds) })} placeholder="启动超时秒数" />
        <input className={cx(inputClass, "bg-white")} value={String(agent.shutdownTimeoutSeconds)} onChange={(event) => onChange({ ...agent, shutdownTimeoutSeconds: parseNumber(event.target.value, agent.shutdownTimeoutSeconds) })} placeholder="关闭超时秒数" />
      </div>
      <textarea className={cx(textareaClass, "min-h-16 bg-white")} value={agent.description} onChange={(event) => onChange({ ...agent, description: event.target.value })} placeholder="描述" />
      <textarea className={cx(textareaClass, "min-h-24 bg-white font-mono text-[12px]")} value={formatLauncher(agent.launcher)} onChange={(event) => onChange({ ...agent, launcher: parseLauncher(event.target.value) })} placeholder="每行一个启动命令片段" />
    </EditorCard>
  );
}
