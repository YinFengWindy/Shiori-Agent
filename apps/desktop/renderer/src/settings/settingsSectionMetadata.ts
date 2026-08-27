import type { SettingsSectionId } from "./SettingsSidebar";

export type SettingsSubsection = {
  id: string;
  label: string;
};

/** Lists the available subsections for every settings domain. */
export const settingsSubsections: Record<SettingsSectionId, SettingsSubsection[]> = {
  models: [
    { id: "catalog", label: "模型注册" },
  ],
  channels: [
    { id: "telegram", label: "Telegram" },
    { id: "qq", label: "QQ" },
    { id: "qqbot", label: "QQBot" },
  ],
  memory: [
    { id: "general", label: "基础" },
    { id: "embedding", label: "Embedding" },
  ],
  integrations: [
    { id: "novelai", label: "NovelAI" },
  ],
  voice: [
    { id: "provider", label: "供应商" },
    { id: "input", label: "输入" },
  ],
  advanced: [
    { id: "general", label: "基础" },
  ],
};

/** Builds the initial active subsection for each settings domain. */
export function createInitialSettingsSubsectionState(): Record<SettingsSectionId, string> {
  return {
    models: settingsSubsections.models[0]?.id ?? "",
    channels: settingsSubsections.channels[0]?.id ?? "",
    memory: settingsSubsections.memory[0]?.id ?? "",
    integrations: settingsSubsections.integrations[0]?.id ?? "",
    voice: settingsSubsections.voice[0]?.id ?? "",
    advanced: settingsSubsections.advanced[0]?.id ?? "",
  };
}

/** Resolves an active subsection, falling back to the first available option. */
export function resolveSettingsSubsectionId(
  sectionId: SettingsSectionId,
  activeSubsections: Record<SettingsSectionId, string>,
): string | null {
  const subsections = settingsSubsections[sectionId];
  const activeId = activeSubsections[sectionId];
  return subsections.some((item) => item.id === activeId)
    ? activeId
    : (subsections[0]?.id ?? null);
}
