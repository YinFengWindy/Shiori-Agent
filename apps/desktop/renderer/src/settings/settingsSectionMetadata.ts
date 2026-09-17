import { pluginUiRegistry } from "../plugins/pluginUiRegistry";
import { registerBuiltinSettingsSections } from "./registerBuiltinSettingsSections";
import type { SettingsSectionId } from "./SettingsSidebar";
import type { SettingsSubsection } from "./settingsPageTypes";

export type { SettingsSubsection };

registerBuiltinSettingsSections();

/**
 * Returns the sub-navigation tabs a section declared, plus (issue #230) any
 * `settings.subsection` entries nested under it — today only `"plugins"`
 * has any. `isPluginEnabled` filters the nested ones the same way every
 * other plugin contribution is filtered (AC 3: disabling a plugin drops its
 * subtab immediately); omit it to see every registered subtab regardless of
 * enabled state (used when resolving a not-yet-visited section's default
 * subtab — see `useSettingsSubsectionMemory`).
 */
export function getSettingsSubsections(
  sectionId: SettingsSectionId,
  isPluginEnabled?: (pluginId: string) => boolean,
): SettingsSubsection[] {
  const entry = pluginUiRegistry.getSettingsSection(sectionId);
  if (!entry) return [];
  const nested = pluginUiRegistry
    .listSettingsSubsections(entry.id, isPluginEnabled)
    .map((item) => ({ id: item.id, label: item.label }));
  return [...entry.subsections, ...nested];
}

/** Resolves an active subsection, falling back to the first available (visible) option. */
export function resolveSettingsSubsectionId(
  sectionId: SettingsSectionId,
  activeSubsections: Record<string, string>,
  isPluginEnabled?: (pluginId: string) => boolean,
): string | null {
  const subsections = getSettingsSubsections(sectionId, isPluginEnabled);
  const activeId = activeSubsections[sectionId];
  return subsections.some((item) => item.id === activeId)
    ? activeId
    : (subsections[0]?.id ?? null);
}
