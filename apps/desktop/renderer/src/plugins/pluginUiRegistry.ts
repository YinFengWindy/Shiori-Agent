import type React from "react";
import type {
  SettingsSectionEditorProps,
  SettingsSubsection,
  StandaloneSettingsSectionProps,
} from "../settings/settingsPageTypes";

/**
 * The UI extension points a plugin (or the core) can contribute to.
 *
 * `settings.section` and `nav.page` are #179's first batch. `role.assets`
 * arrived with #181-D, when the desktop pet's package manager became the
 * first real thing that had to live inside an existing host page rather than
 * own a page of its own — which is the condition #174's scope note named
 * ("等有真实插件需求再开") rather than a slot invented ahead of a use.
 */
export type PluginUiSlot = "settings.section" | "nav.page" | "role.assets";

/**
 * A settings section backed by the shared settings draft (`SettingsFormData`)
 * and its autosave queue. Only the built-in, TOML-backed domains use this —
 * they are the only sections that share one document and one save
 * transaction across every section at once.
 */
export type EditorSettingsSectionEntry = {
  kind: "editor";
  slot: "settings.section";
  id: string;
  label: string;
  subsections: SettingsSubsection[];
  /** Absent for built-in sections; present for plugin-contributed ones. */
  pluginId?: string;
  Component: React.ComponentType<SettingsSectionEditorProps>;
};

/**
 * A settings section that owns its own data end to end (schema-driven
 * plugin forms, custom plugin React components, and the built-in About
 * page). It never touches the shared settings draft, so it can render
 * before that draft has loaded and never blocks on it. SettingsPage owns
 * the surrounding surface, padding and scroll area; components render content.
 */
export type StandaloneSettingsSectionEntry = {
  kind: "standalone";
  slot: "settings.section";
  id: string;
  label: string;
  subsections: SettingsSubsection[];
  pluginId?: string;
  Component: React.ComponentType<StandaloneSettingsSectionProps>;
};

export type SettingsSectionEntry = EditorSettingsSectionEntry | StandaloneSettingsSectionEntry;

/**
 * A settings.section registered as a subtab of a built-in parent section
 * (issue #230). Today the only parent is `"plugins"`: instead of a plugin's
 * own settings surfacing as a top-level sidebar entry (issue #174's
 * original shape), it becomes one subtab alongside "已安装" inside the
 * 「插件」 section. Nesting is exactly one level — this entry cannot itself
 * have subsections — matching the owner's decision that a second nesting
 * level is out of scope.
 */
export type SettingsSubsectionEntry = {
  slot: "settings.subsection";
  parentId: string;
  id: string;
  label: string;
  pluginId?: string;
  Component: React.ComponentType<StandaloneSettingsSectionProps>;
};

/**
 * Props injected into a plugin-contributed full-page navigation surface.
 *
 * `activeRoleId` mirrors the shell's own "role currently open in chat"
 * state (`DesktopAppFrame`'s own `activeRoleId` prop) — it is ambient
 * context every nav.page occupant may want (e.g. to prefill a form with the
 * role the user was just chatting with), not something specific to one
 * plugin. It is optional and best-effort: it reflects whatever role was
 * last opened via chat, empty string when none has been, and is not
 * threaded to any other plugin surface (settings.section, DesktopSurface).
 */
export type PluginNavPageProps = {
  /** Returns from a full-window plugin page to the chat workspace. */
  onExit?: () => void;
  pageId: string;
  activeRoleId?: string;
};

/**
 * Props injected into a plugin-contributed sidebar that renders into the
 * host's resizable `sidebar-track` while this page is active (issue #226
 * gap A). Deliberately the same shape `RoleSidebar`/`SettingsSidebar`
 * already receive from `DesktopAppFrame` — `animating`/`collapsed`/`width`
 * so the occupant can match the host's collapse/resize transitions, and
 * `onBeginResize` so it can wire the same drag handle those sidebars
 * render themselves. `activeRoleId` is intentionally not included here:
 * unlike `PluginNavPageProps`, this is a second, separate mount point the
 * host renders as a sibling of the page component, not a child of it, and
 * `usePluginUiVisibility`/`DesktopAppFrame` have no reason to know a
 * plugin's sidebar wants ambient role context a plugin-owned store
 * (see novelai's `novelAiPageStore.ts`) can relay just as well.
 */
export type PluginNavPageSidebarProps = {
  pageId: string;
  animating: boolean;
  collapsed: boolean;
  width: number;
  onBeginResize: (event: React.PointerEvent<HTMLDivElement>) => void;
};

/**
 * Props injected into a plugin-contributed panel on the role asset page.
 *
 * Deliberately just the two things a panel cannot work out for itself: which
 * role's asset library is open, and whether the host is currently in a state
 * where input must be refused (bridge down, or a save in flight). Everything
 * the panel *shows* is its own data, fetched through its own
 * `plugin.<id>.*` client — the host does not thread a plugin's domain
 * through `RoleRecord` on its behalf, which is the coupling #181 exists to
 * remove.
 *
 * `roleId` is empty when no role is open; a panel should render nothing
 * rather than guess.
 */
export type PluginRoleAssetsProps = {
  roleId: string;
  disabled: boolean;
  /** Refreshes core and independent plugin projections after an asset mutation. */
  onRoleDataChanged: () => void;
};

/** One plugin's panel inside the role asset page. */
export type RoleAssetsPanelEntry = {
  slot: "role.assets";
  id: string;
  pluginId?: string;
  Component: React.ComponentType<PluginRoleAssetsProps>;
};

export type NavPageEntry = {
  slot: "nav.page";
  id: string;
  label: string;
  icon?: React.ComponentType<{ className?: string }>;
  pluginId?: string;
  Component: React.ComponentType<PluginNavPageProps>;
  /** Full-window contributions own their surrounding presentation and exit control. */
  presentation?: "workspace" | "fullscreen";
  /**
   * Optional (issue #226 gap A): when present, `DesktopAppFrame` renders it
   * into the host's resizable sidebar track instead of falling back to
   * `RoleSidebar` while this page is active. Absent for every entry that
   * doesn't need one — most nav.page occupants have no sidebar at all.
   */
  Sidebar?: React.ComponentType<PluginNavPageSidebarProps>;
  /**
   * Optional (issue #226 gap B): called synchronously when the nav rail
   * entry is clicked. A non-empty string refuses the navigation and is the
   * reason shown to the user (owner decision: 拦住 + 给提示, not a silent
   * refusal); `null`/absent means selectable, today's behaviour. One field
   * with one meaning, rather than a boolean plus a parallel message field
   * that could disagree with it.
   */
  selectBlockedReason?: () => string | null;
};

/**
 * Builds a nav-rail entry's click handler around its optional
 * `selectBlockedReason` guard (issue #226 gap B): when it currently returns
 * a reason, the click is refused and `onBlocked` is called with that reason
 * instead of `onSelect` — the host surfaces it (see `DesktopAppFrame`'s
 * `navBlockedMessage`), it does not invent the message itself. An entry
 * with no `selectBlockedReason` is always selectable, today's behaviour.
 */
export function guardedNavPageSelect(
  entry: Pick<NavPageEntry, "selectBlockedReason">,
  onSelect: () => void,
  onBlocked: (reason: string) => void,
): () => void {
  return () => {
    const reason = entry.selectBlockedReason?.();
    if (reason) {
      onBlocked(reason);
      return;
    }
    onSelect();
  };
}

type Origin = "builtin" | "plugin";

/**
 * Whether one registry entry is visible right now: a built-in entry (no
 * `pluginId`) always is; a plugin-owned entry only while that plugin is
 * enabled. The single rule shared by nav rail, settings sidebar, the
 * settings page and the active plugin-page view (see `usePluginUiVisibility`).
 */
export function isPluginContributionVisible(
  pluginId: string | undefined,
  isPluginEnabled: (pluginId: string) => boolean,
): boolean {
  return !pluginId || isPluginEnabled(pluginId);
}

/**
 * Aggregates settings.section and nav.page contributions from the core
 * (built-in entries) and from plugins (compiled in at build time via
 * `pluginUiModules.ts`). Built-in sections are registered through this same
 * registry rather than switched on directly, so the dynamic settings page
 * and the plugin slot mechanism share one real consumption path instead of
 * the slot machinery going unexercised by anything but plugins.
 */
class PluginUiRegistry {
  private readonly settingsSections = new Map<string, { origin: Origin; entry: SettingsSectionEntry }>();
  private readonly settingsSubsections = new Map<string, Map<string, { origin: Origin; entry: SettingsSubsectionEntry }>>();
  private readonly navPages = new Map<string, { origin: Origin; entry: NavPageEntry }>();
  private readonly roleAssetsPanels = new Map<string, { origin: Origin; entry: RoleAssetsPanelEntry }>();

  /** Registers a settings.section entry; a duplicate id is warned about and skipped. */
  registerSettingsSection(entry: SettingsSectionEntry, origin: Origin = "plugin"): void {
    if (this.settingsSections.has(entry.id)) {
      console.warn(`[pluginUiRegistry] settings.section id 重复，已跳过: ${entry.id}`);
      return;
    }
    this.settingsSections.set(entry.id, { origin, entry });
  }

  /**
   * Registers a settings.subsection entry under a parent settings.section
   * (issue #230). A duplicate `(parentId, id)` pair is warned about and
   * skipped rather than overwritten — this is the mechanism that makes a
   * hand-written plugin settings.section win over the config-schema
   * auto-registration in `pluginSettingsAutoRegistration.ts` (AC 6): the
   * hand-written one is always registered first (build-time glob / runtime
   * synchronizeUi both run before the roster refresh that drives
   * auto-registration), so the later attempt hits this guard.
   */
  registerSettingsSubsection(entry: SettingsSubsectionEntry, origin: Origin = "plugin"): void {
    let group = this.settingsSubsections.get(entry.parentId);
    if (!group) {
      group = new Map();
      this.settingsSubsections.set(entry.parentId, group);
    }
    if (group.has(entry.id)) {
      console.warn(`[pluginUiRegistry] settings.subsection id 重复 (parent=${entry.parentId})，已跳过: ${entry.id}`);
      return;
    }
    group.set(entry.id, { origin, entry });
  }

  /** Removes one settings.subsection entry (used when a plugin loses its config schema or leaves the roster). */
  unregisterSettingsSubsection(parentId: string, id: string): void {
    this.settingsSubsections.get(parentId)?.delete(id);
  }

  /** Registers a nav.page entry; a duplicate id is warned about and skipped. */
  registerNavPage(entry: NavPageEntry, origin: Origin = "plugin"): void {
    if (this.navPages.has(entry.id)) {
      console.warn(`[pluginUiRegistry] nav.page id 重复，已跳过: ${entry.id}`);
      return;
    }
    this.navPages.set(entry.id, { origin, entry });
  }

  /** Registers a role.assets panel; a duplicate id is warned about and skipped. */
  registerRoleAssetsPanel(entry: RoleAssetsPanelEntry, origin: Origin = "plugin"): void {
    if (this.roleAssetsPanels.has(entry.id)) {
      console.warn(`[pluginUiRegistry] role.assets id 重复，已跳过: ${entry.id}`);
      return;
    }
    this.roleAssetsPanels.set(entry.id, { origin, entry });
  }

  /** Removes every contribution owned by one plugin (used by tests and hot-toggle cleanup). */
  unregisterPlugin(pluginId: string): void {
    for (const [id, { entry }] of this.settingsSections) {
      if (entry.pluginId === pluginId) this.settingsSections.delete(id);
    }
    for (const group of this.settingsSubsections.values()) {
      for (const [id, { entry }] of group) {
        if (entry.pluginId === pluginId) group.delete(id);
      }
    }
    for (const [id, { entry }] of this.navPages) {
      if (entry.pluginId === pluginId) this.navPages.delete(id);
    }
    for (const [id, { entry }] of this.roleAssetsPanels) {
      if (entry.pluginId === pluginId) this.roleAssetsPanels.delete(id);
    }
  }

  /**
   * Lists settings.section entries, built-ins first, each group in
   * registration order; optionally filtered to entries that are either
   * built-in or owned by a currently-enabled plugin.
   */
  listSettingsSections(isPluginEnabled?: (pluginId: string) => boolean): SettingsSectionEntry[] {
    return this.listOrdered(this.settingsSections, isPluginEnabled);
  }

  /** Lists nav.page entries with the same built-in-first ordering and filtering. */
  listNavPages(isPluginEnabled?: (pluginId: string) => boolean): NavPageEntry[] {
    return this.listOrdered(this.navPages, isPluginEnabled);
  }

  /** Lists role.assets panels with the same built-in-first ordering and filtering. */
  listRoleAssetsPanels(isPluginEnabled?: (pluginId: string) => boolean): RoleAssetsPanelEntry[] {
    return this.listOrdered(this.roleAssetsPanels, isPluginEnabled);
  }

  /** Lists a parent settings.section's registered subtabs, built-in-first, filtered the same way as any other slot. */
  listSettingsSubsections(parentId: string, isPluginEnabled?: (pluginId: string) => boolean): SettingsSubsectionEntry[] {
    const group = this.settingsSubsections.get(parentId);
    if (!group) return [];
    return this.listOrdered(group, isPluginEnabled);
  }

  getSettingsSection(id: string): SettingsSectionEntry | undefined {
    return this.settingsSections.get(id)?.entry;
  }

  getSettingsSubsection(parentId: string, id: string): SettingsSubsectionEntry | undefined {
    return this.settingsSubsections.get(parentId)?.get(id)?.entry;
  }

  getNavPage(id: string): NavPageEntry | undefined {
    return this.navPages.get(id)?.entry;
  }

  private listOrdered<T extends { pluginId?: string }>(
    source: Map<string, { origin: Origin; entry: T }>,
    isPluginEnabled?: (pluginId: string) => boolean,
  ): T[] {
    const visible = [...source.values()].filter(({ entry }) => (
      !isPluginEnabled || isPluginContributionVisible(entry.pluginId, isPluginEnabled)
    ));
    const builtins = visible.filter((item) => item.origin === "builtin").map((item) => item.entry);
    const plugins = visible.filter((item) => item.origin === "plugin").map((item) => item.entry);
    return [...builtins, ...plugins];
  }
}

/** Process-wide plugin UI registry; populated at module load by builtins and plugin modules. */
export const pluginUiRegistry = new PluginUiRegistry();

/** Exposed for tests that need an isolated registry instead of the shared singleton. */
export { PluginUiRegistry };
