import { useCallback, useState } from "react";
import { resolveSettingsSubsectionId } from "./settingsSectionMetadata";
import type { SettingsSectionId } from "./SettingsSidebar";

export type SettingsSubsectionMemory = {
  /** The last remembered subtab per settings section id. */
  activeSubsections: Record<string, string>;
  /**
   * Resolves the subtab that should be showing for `sectionId` right now:
   * the remembered one if it is still a valid option (and, when
   * `isPluginEnabled` is given, still visible), else the section's first
   * subtab. Delegates to `settingsSectionMetadata`'s
   * `resolveSettingsSubsectionId` against this hook's own record, so every
   * caller resolves against the same one source of truth instead of each
   * reaching into registry/metadata helpers with its own copy of the record.
   */
  resolve: (sectionId: SettingsSectionId, isPluginEnabled?: (pluginId: string) => boolean) => string | null;
  /** Records `sectionId`'s active subtab; a no-op if it is already that value. */
  remember: (sectionId: string, subsectionId: string) => void;
};

/**
 * Owns the "last active subtab per settings section" record (issue #230 AC
 * 4) and the one place that resolves and writes it back. Lifted out of
 * `SettingsPage`'s own state (which reset on every section-kind switch) and
 * out of `useNavigationHistory` (which had no business owning settings
 * metadata resolution — a navigation hook importing
 * `settingsSectionMetadata` was reaching outside its own domain) into its
 * own hook so both call sites share one record and one merge
 * implementation instead of two copies of the same
 * `current[x] === y ? current : {...current, [x]: y}` guard.
 *
 * `resolve` is also how issue #230 AC 3's fallback commits itself:
 * `resolveSettingsSubsectionId` already substitutes a visible subtab when
 * the remembered one belongs to a just-disabled plugin, but that alone only
 * fixes what's *displayed* — nothing wrote the fallback back into the
 * record, so re-enabling that plugin later in the same session would make
 * the stale remembered id valid again and silently snap the page back to
 * it. The caller (`SettingsPage`) is responsible for calling `remember`
 * once it observes `resolve`'s answer disagreeing with the record — see its
 * write-back effect — because only the caller knows the currently rendered
 * section and its live `isPluginEnabled` filter.
 */
export function useSettingsSubsectionMemory(): SettingsSubsectionMemory {
  const [activeSubsections, setActiveSubsections] = useState<Record<string, string>>({});

  const remember = useCallback((sectionId: string, subsectionId: string) => {
    setActiveSubsections((current) => (
      current[sectionId] === subsectionId ? current : { ...current, [sectionId]: subsectionId }
    ));
  }, []);

  const resolve = useCallback(
    (sectionId: SettingsSectionId, isPluginEnabled?: (pluginId: string) => boolean) => (
      resolveSettingsSubsectionId(sectionId, activeSubsections, isPluginEnabled)
    ),
    [activeSubsections],
  );

  return { activeSubsections, resolve, remember };
}
