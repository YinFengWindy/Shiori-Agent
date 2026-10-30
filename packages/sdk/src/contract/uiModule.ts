/**
 * The plugin UI module contract: what a plugin's `ui/index.tsx` default-exports
 * and the props each contributed component receives.
 */
import type React from "react";
import type { PluginRpcClient } from "../rpc";
import type { PluginChatImageActionProps, PluginRoleSettingsContribution } from "./features";
import type { PluginHostServices } from "./hostServices";
import type {
  PluginAccountDetailProps,
  PluginNavPageProps,
  PluginNavPageSidebarProps,
  PluginRoleAssetsProps,
  StandaloneSettingsSectionProps,
} from "./slots";

/**
 * What the host injects into every bound plugin component (nav.page and its
 * sidebar, a custom settings.section, role.assets): its namespace-scoped RPC
 * client and, since runtime API 2.4.0, the host services as a prop — so a
 * precompiled external package, which cannot import the host's React
 * context, reaches `host.feedback` and `host.ui.InlineError` too.
 */
export type PluginInjectedProps = { client: PluginRpcClient; host: PluginHostServices };

/**
 * Props a plugin-authored nav.page component receives: the base slot props
 * plus the injected client and host services.
 */
export type PluginNavPageComponentProps = PluginNavPageProps & PluginInjectedProps;

/**
 * Props a plugin-authored nav.page sidebar receives: the base slot props
 * (see `PluginNavPageSidebarProps`) plus its injected, namespace-scoped RPC
 * client — same treatment as the page component itself.
 */
export type PluginNavPageSidebarComponentProps = PluginNavPageSidebarProps & PluginInjectedProps;

/**
 * Props a plugin-authored custom settings.section component receives: the
 * base slot props plus its injected, namespace-scoped RPC client.
 */
export type PluginSettingsSectionComponentProps = StandaloneSettingsSectionProps & PluginInjectedProps;

/**
 * One plugin's settings.section contribution: either a schema auto-form or
 * a custom component. Registers as a single subtab under the built-in
 * 「插件」 section (issue #230) — nesting is exactly one level, so this
 * carries no `subsections` of its own.
 */
export type PluginSettingsSectionContribution =
  | { kind: "schema"; label: string }
  | { kind: "component"; label: string; component: React.ComponentType<PluginSettingsSectionComponentProps> };

/**
 * Props a plugin-authored role.assets panel receives: the base slot props plus
 * its injected, namespace-scoped RPC client — the same treatment the other two
 * slots get, and the only way such a panel can reach any data at all.
 */
export type PluginRoleAssetsComponentProps = PluginRoleAssetsProps & PluginInjectedProps;

/** One plugin's panel inside the role asset page. */
export type PluginRoleAssetsContribution = {
  component: React.ComponentType<PluginRoleAssetsComponentProps>;
};

/** Plugin-authored account controls receive a scoped RPC client and host services. */
export type PluginAccountDetailComponentProps = PluginAccountDetailProps & PluginInjectedProps;

/** The chat sidebar tells the affection block which role is open; nothing of the plugin's data. */
export type PluginChatAffectionProps = {
  /** The role whose chat is open. The plugin reads its own data for it. */
  roleId: string;
};

/** Chat affection block: slot props plus the injected client and host services. */
export type PluginChatAffectionComponentProps = PluginChatAffectionProps & PluginInjectedProps;

/** The role page tells the affection tab which role is open and whether the bridge is up. */
export type PluginRoleAffectionProps = {
  roleId: string;
  bridgeReady: boolean;
};

/** Role affection tab: slot props plus the injected client and host services. */
export type PluginRoleAffectionComponentProps = PluginRoleAffectionProps & PluginInjectedProps;

/**
 * The chat task panel tells the scheduled-task block which role is open and
 * which of the block's own views is shown. The block lists its jobs as one
 * group of the panel's task list while `view` is empty. Any other value is a
 * view the block defined (a detail, a form …): the block then fills the whole
 * panel and draws its own header. The panel keeps `view` across its re-renders
 * and resets it when the role changes.
 */
export type PluginRoleTasksProps = {
  roleId: string;
  view: string;
  /** Shows one of the block's views; `""` returns to the panel's task list. */
  onViewChange: (view: string) => void;
};

/** Role task block: slot props plus the injected client and host services. */
export type PluginRoleTasksComponentProps = PluginRoleTasksProps & PluginInjectedProps;

/** One platform's new-account and connection controls, opened from a role's account page. */
export type PluginAccountDetailContribution = {
  /** Platform name in the role page's add-account choice. */
  label: string;
  icon?: React.ComponentType<{ className?: string }>;
  component: React.ComponentType<PluginAccountDetailComponentProps>;
};

/** One plugin's full-page navigation entry (nav rail item, page and optional sidebar). */
export type PluginNavPageContribution = {
  label: string;
  icon?: React.ComponentType<{ className?: string }>;
  component: React.ComponentType<PluginNavPageComponentProps>;
  presentation?: "workspace" | "fullscreen";
  /** Optional (issue #226 gap A) — see `NavPageEntry.Sidebar`. */
  sidebar?: React.ComponentType<PluginNavPageSidebarComponentProps>;
  /** Optional (issue #226 gap B) — see `NavPageEntry.selectBlockedReason`. */
  selectBlockedReason?: (services: PluginHostServices) => string | null;
};

/**
 * The shape a plugin's `ui/index.tsx` default-exports to participate in
 * `settings.section`, `nav.page` and/or `role.assets`. A plugin id is required
 * (it scopes both its own RPC namespace and hot enable/disable filtering);
 * every slot is optional since a plugin may only need one, or a config-only
 * plugin may only need the schema form.
 */
export type PluginUiModule = {
  pluginId: string;
  settingsSection?: PluginSettingsSectionContribution;
  navPage?: PluginNavPageContribution;
  roleAssets?: PluginRoleAssetsContribution;
  accountDetail?: PluginAccountDetailContribution;
  roleSettings?: PluginRoleSettingsContribution;
  chatImageActions?: React.ComponentType<PluginChatImageActionProps>;
  /** 「好感度」 tab on the role page. Absent means the host hides that tab. */
  roleAffection?: React.ComponentType<PluginRoleAffectionComponentProps>;
  /** The chat status sidebar's affection block (meter, relationship tags, loneliness). */
  chatAffection?: React.ComponentType<PluginChatAffectionComponentProps>;
  /** The chat task panel's scheduled-task block. Absent means the panel lists only the host's tasks. */
  roleTasks?: React.ComponentType<PluginRoleTasksComponentProps>;
};
