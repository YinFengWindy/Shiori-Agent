/** Props the host injects into each plugin UI slot (before the injected `client` and `host`). */
import type React from "react";
import type { AccountSnapshot } from "../account/account";

/** Account null requests a plugin-owned new-account draft; existing accounts open the same detail surface. */
export type PluginAccountDetailProps = {
  account: AccountSnapshot | null;
  /**
   * The role whose account page opened this detail. A new account is created
   * for it: plugins pass it with every create, save, connect, and login call.
   */
  roleId: string;
  /** Refreshes host identity; a created account ID switches the current detail to that record. */
  onChanged: (accountId?: string) => void;
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
  /** Opens this page's own plugin settings tab (e.g. from a "not configured" error). */
  onOpenPluginSettings?: () => void;
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
  /**
   * Call after navigating inside the page from the sidebar: host views close
   * the compact overlay drawer on navigation, but a plugin's own view switch
   * is invisible to the host.
   */
  onNavigate?: () => void;
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

/** Props for a settings section that owns its own data (no shared draft). */
export type StandaloneSettingsSectionProps = {
  subsectionId: string;
  /**
   * Opens another subsection of the same section — how 「插件」's list
   * reaches a plugin's nested settings page. Absent where a component is
   * mounted outside `SettingsPage`.
   */
  onSelectSubsection?: (subsectionId: string) => void;
};
