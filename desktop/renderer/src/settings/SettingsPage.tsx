import { useDeferredValue, useEffect, useState } from "react";
import { type SettingsSectionId, settingsSections } from "./SettingsSidebar";
import { SettingsSectionContent } from "./SettingsSectionContent";
import { cloneSettings, settingsEqual } from "./settingsFormHelpers";
import { settingsSubsections } from "./settingsMetadata";
import { cardClass, cx, ghostButtonClass, primaryButtonClass } from "../shared/styles";
import { ResetIcon, SaveIcon } from "../shared/icons";
import type { RoleRecord, SettingsFormData, SettingsSnapshot } from "../shared/types";

type SavePhase =
  | "idle"
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

/** Renders the desktop settings page and keeps save/restart semantics unchanged while delegating UI sections out. */
export function SettingsPage({ bridgeReady, search, section, onMetaChange }: SettingsPageProps) {
  const [snapshot, setSnapshot] = useState<SettingsSnapshot | null>(null);
  const [draft, setDraft] = useState<SettingsFormData | null>(null);
  const [roles, setRoles] = useState<RoleRecord[]>([]);
  const [loadError, setLoadError] = useState("");
  const [savePhase, setSavePhase] = useState<SavePhase>("idle");
  const [statusMessage, setStatusMessage] = useState("");
  const [activeSubsections, setActiveSubsections] = useState<Record<SettingsSectionId, string>>(createInitialSubsectionState);
  const deferredSearch = useDeferredValue(search.trim().toLowerCase());

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
        if (rolesResponse.error) {
          throw new Error(rolesResponse.error.message);
        }
        const nextFormData = cloneSettings(nextSnapshot.formData);
        nextFormData.channels.roleBindings = nextBindings.bindings;
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

  const visibleSections = settingsSections.filter((item) => {
    if (!deferredSearch) return true;
    return item.label.toLowerCase().includes(deferredSearch) || item.id.toLowerCase().includes(deferredSearch);
  });
  const currentSection = visibleSections.find((item) => item.id === section) ?? visibleSections[0] ?? null;
  const currentSectionId = currentSection?.id ?? null;
  const visibleSubsections = currentSectionId ? settingsSubsections[currentSectionId] : [];
  const currentSubsectionId = currentSectionId
    ? (visibleSubsections.some((item) => item.id === activeSubsections[currentSectionId])
      ? activeSubsections[currentSectionId]
      : (visibleSubsections[0]?.id ?? ""))
    : "";
  const isDirty = Boolean(snapshot && !settingsEqual(snapshot.formData, draft));

  function updateActiveSubsection(nextId: string): void {
    if (!currentSectionId) return;
    setActiveSubsections((current) => (
      current[currentSectionId] === nextId
        ? current
        : { ...current, [currentSectionId]: nextId }
    ));
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

      <div className="border-b border-[#E8EBF0] bg-[#F7F8FB] px-8 py-5">
        <div className="mx-auto flex w-full max-w-[980px] items-center gap-5">
          <div className="min-w-0 flex-1">
            <div className="text-[11px] font-medium uppercase tracking-[0.12em] text-[#8B95A3]">
              {currentSection?.label ?? "设置"}
            </div>
            <div className="mt-1 text-sm text-[#606A78]">
              {isDirty ? "有未保存修改" : "当前内容已与配置文件同步"}
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-center gap-2">
            {visibleSubsections.map((item) => (
              <button
                key={item.id}
                className={cx(
                  "rounded-md border px-3 py-2 text-sm transition focus:outline-none",
                  item.id === currentSubsectionId
                    ? "border-[#D9E0E8] bg-white text-[#1F2430] shadow-[0_6px_18px_rgba(15,23,42,0.06)]"
                    : "border-transparent bg-transparent text-[#67717E] hover:border-[#D9E0E8] hover:bg-white/70",
                )}
                type="button"
                onClick={() => updateActiveSubsection(item.id)}
              >
                {item.label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2.5">
            <button
              className={cx("inline-flex items-center gap-2 rounded-md px-4 py-2 text-sm", ghostButtonClass)}
              type="button"
              aria-label="重置"
              onClick={reset}
              disabled={!isDirty}
            >
              <ResetIcon className="h-[16px] w-[16px] fill-current" />
              <span>重置</span>
            </button>
            <button
              className={cx("inline-flex items-center gap-2 rounded-md px-4 py-2 text-sm", primaryButtonClass)}
              type="button"
              aria-label="保存并重启"
              onClick={() => void save()}
              disabled={!bridgeReady || !isDirty || savePhase === "saving"}
            >
              <SaveIcon className="h-[16px] w-[16px] fill-current" />
              <span>{savePhase === "saving" ? "保存中..." : "保存并重启"}</span>
            </button>
          </div>
        </div>
      </div>

      <div className="relative scrollbar-soft overflow-y-auto px-8 py-8">
        <div className="mx-auto w-full max-w-[980px]">
          {!currentSectionId ? (
            <div className={cx(cardClass, "grid min-h-[240px] place-items-center border-dashed text-sm text-[#7f8490]")}>
              没有匹配的设置项
            </div>
          ) : (
            <SettingsSectionContent
              section={currentSectionId}
              subsectionId={currentSubsectionId}
              draft={draft}
              roles={roles}
              dirty={isDirty}
              updateDraft={updateDraft}
              updateProactiveTargetChannel={updateProactiveTargetChannel}
              updateProactiveTargetRoleId={updateProactiveTargetRoleId}
            />
          )}
        </div>
      </div>
    </section>
  );
}
