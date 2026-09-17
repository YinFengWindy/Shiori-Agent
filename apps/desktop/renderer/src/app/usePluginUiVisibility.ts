import { useCallback, useMemo } from "react";
import { isPluginContributionVisible, pluginUiRegistry, type NavPageEntry } from "../plugins/pluginUiRegistry";
import { usePluginEnabledState } from "../plugins/usePluginEnabledState";
import type { PluginEnabledPredicate } from "../plugins/pluginEnabledStateStore";
import { listSettingsSidebarSections, type SettingsSectionId } from "../settings/SettingsSidebar";

export type PluginUiVisibility = {
  /** nav.page entries visible right now: built-ins first, then every currently-enabled plugin. */
  pluginNavPages: NavPageEntry[];
  /** Sidebar entries for every currently visible settings.section. */
  settingsSidebarSections: Array<{ id: SettingsSectionId; label: string }>;
  /** Whether one settings.section id is visible right now (hides a just-disabled plugin's section immediately, issue #174 AC 3). */
  isSectionVisible: (sectionId: SettingsSectionId) => boolean;
  /** Resolves a plugin-page's nav.page entry, but only while it is currently visible. */
  resolveVisibleNavPage: (pageId: string) => NavPageEntry | undefined;
  /**
   * The raw predicate, exposed for callers that need subtab-level filtering
   * (issue #230 AC 3) — `isSectionVisible` only answers for a whole
   * settings.section id and cannot express "which of 「插件」's own subtabs
   * are visible right now".
   */
  isPluginEnabled: PluginEnabledPredicate;
};

/**
 * Centralizes "is this plugin's UI contribution visible right now" for the
 * desktop shell. Nav rail, settings sidebar, the settings page and the
 * active plugin-page view all need the same answer (built-in entries always
 * visible, plugin-owned entries only while that plugin is enabled); before
 * this hook `DesktopAppFrame` computed it three separate times with three
 * separate inline predicates.
 */
export function usePluginUiVisibility(): PluginUiVisibility {
  const isPluginEnabled = usePluginEnabledState();

  const pluginNavPages = useMemo(
    () => pluginUiRegistry.listNavPages(isPluginEnabled),
    [isPluginEnabled],
  );

  const settingsSidebarSections = useMemo(
    () => listSettingsSidebarSections(isPluginEnabled),
    [isPluginEnabled],
  );

  const isSectionVisible = useCallback(
    (sectionId: SettingsSectionId) => {
      const entry = pluginUiRegistry.getSettingsSection(sectionId);
      return Boolean(entry) && isPluginContributionVisible(entry?.pluginId, isPluginEnabled);
    },
    [isPluginEnabled],
  );

  const resolveVisibleNavPage = useCallback(
    (pageId: string) => {
      const entry = pluginUiRegistry.getNavPage(pageId);
      return entry && isPluginContributionVisible(entry.pluginId, isPluginEnabled) ? entry : undefined;
    },
    [isPluginEnabled],
  );

  return { pluginNavPages, settingsSidebarSections, isSectionVisible, resolveVisibleNavPage, isPluginEnabled };
}
