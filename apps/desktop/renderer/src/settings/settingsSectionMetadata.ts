import { pluginUiRegistry, type SettingsSectionEntry } from "../plugins/pluginUiRegistry";
import { registerBuiltinSettingsSections } from "./registerBuiltinSettingsSections";
import type { SettingsSectionId } from "./SettingsSidebar";
import type { SettingsSubsection } from "./settingsPageTypes";

export type { SettingsSubsection };

registerBuiltinSettingsSections();

/** Lists every currently registered settings section, built-ins first. */
export function listSettingsSections(
  isPluginEnabled?: (pluginId: string) => boolean,
): SettingsSectionEntry[] {
  return pluginUiRegistry.listSettingsSections(isPluginEnabled);
}

/**
 * Returns the sub-navigation tabs a section declared, plus (issue #230) any
 * `settings.subsection` entries nested under it — today only `"plugins"`
 * has any. `isPluginEnabled` filters the nested ones the same way every
 * other plugin contribution is filtered (AC 3: disabling a plugin drops its
 * subtab immediately); omit it to see every registered subtab regardless of
 * enabled state (used for the seed value in `createInitialSettingsSubsectionState`
 * and for defaulting a not-yet-visited section's navigation entry).
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

/**
 * Builds the initial active subsection for every currently registered
 * section. Keyed by plain `string` (not `SettingsSectionId`): this is a
 * dynamic lookup map, not an exhaustively-cased record, and section ids
 * include plugin ids only known at runtime.
 */
export function createInitialSettingsSubsectionState(
  sections: SettingsSectionEntry[] = listSettingsSections(),
): Record<string, string> {
  return Object.fromEntries(
    sections.map((section) => [section.id, getSettingsSubsections(section.id)[0]?.id ?? ""]),
  );
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
