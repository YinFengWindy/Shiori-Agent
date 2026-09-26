import { usePluginRpcClient } from "./usePluginRpcClient";
import { PluginHostServicesProvider } from "./PluginHostServicesProvider";
import { desktopPluginHostServices, type PluginHostServices } from "./pluginHostServices";
import type React from "react";
import { pluginChatImageActionsRegistry, pluginRoleSettingsRegistry, type PluginChatImageActionProps, type PluginRoleSettingsContribution } from "./pluginFeatureRegistry";
import type { StandaloneSettingsSectionProps } from "../settings/settingsPageTypes";
import { createPluginSchemaSettingsSection } from "./pluginSchemaSettingsSectionFactory";
import { type PluginRpcClient } from "./pluginBridgeClient";
import {
  pluginUiRegistry,
  type PluginNavPageProps,
  type PluginNavPageSidebarProps,
  type PluginRoleAssetsProps,
  type PluginRoleMemoryProps,
} from "./pluginUiRegistry";

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

/** Props a memory plugin's role-detail Dashboard receives with its scoped RPC client. */
export type PluginRoleMemoryComponentProps = PluginRoleMemoryProps & PluginInjectedProps;

/** A memory plugin's role.memory contribution. */
export type PluginRoleMemoryContribution = {
  component: React.ComponentType<PluginRoleMemoryComponentProps>;
};

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
  roleMemory?: PluginRoleMemoryContribution;
  roleSettings?: PluginRoleSettingsContribution;
  chatImageActions?: React.ComponentType<PluginChatImageActionProps>;
};

/** Narrows an unknown default export down to a well-formed PluginUiModule, without an unsafe cast. */
function isPluginUiModule(value: unknown): value is PluginUiModule {
  if (value === null || typeof value !== "object") return false;
  return "pluginId" in value && typeof value.pluginId === "string";
}

/**
 * Injects mount-scoped clients and host services into contributed components.
 * Namespace binding expresses cooperation; it is not a same-realm sandbox.
 */
function bindPluginClient<TBaseProps extends object>(
  pluginId: string,
  Component: React.ComponentType<TBaseProps & PluginInjectedProps>,
): React.ComponentType<TBaseProps> {
  return function PluginClientBoundComponent(props: TBaseProps) {
    const client = usePluginRpcClient(pluginId);
    return <PluginHostServicesProvider services={desktopPluginHostServices}>
      <Component {...props} client={client} host={desktopPluginHostServices} />
    </PluginHostServicesProvider>;
  };
}

/**
 * Registers every plugin UI module found by the build-time glob into
 * `pluginUiRegistry`. Pure and DOM-free (only mutates the passed registry)
 * so it is unit-testable with a hand-built `modules` record instead of a
 * real `import.meta.glob` result, which only Vite can produce.
 */
export function applyPluginUiModules(
  modules: Record<string, { default: PluginUiModule }>,
  registry = pluginUiRegistry,
): void {
  for (const [path, mod] of Object.entries(modules)) {
    const uiModule = mod.default;
    if (!isPluginUiModule(uiModule)) {
      console.error(`[pluginUiModules] ${path} 的默认导出不是合法的 PluginUiModule，已跳过`);
      continue;
    }
    const { pluginId, settingsSection, navPage, roleAssets, roleMemory } = uiModule;
    if (uiModule.roleSettings) pluginRoleSettingsRegistry.register({ pluginId, ...uiModule.roleSettings });
    if (uiModule.chatImageActions) pluginChatImageActionsRegistry.register({
      pluginId, Component: uiModule.chatImageActions,
    });
    if (settingsSection) {
      // Registers as a subtab of the built-in "plugins" section rather than
      // a top-level settings.section (issue #230): a plugin's own settings
      // surface lives inside 「插件」, alongside "已安装", instead of
      // flattening the sidebar. This is also what makes a hand-written
      // module win over `pluginSettingsAutoRegistration`'s config-schema
      // auto-registration — this call always runs first (build-time glob /
      // runtime synchronizeUi both resolve before the roster refresh that
      // drives auto-registration), so a later auto-registration attempt for
      // the same plugin id hits `registerSettingsSubsection`'s duplicate
      // guard instead of overwriting this entry.
      registry.registerSettingsSubsection({
        slot: "settings.subsection",
        parentId: "plugins",
        id: pluginId,
        label: settingsSection.label,
        pluginId,
        Component: settingsSection.kind === "schema"
          ? createPluginSchemaSettingsSection(pluginId)
          : bindPluginClient(pluginId, settingsSection.component),
      });
    }
    if (roleAssets) {
      registry.registerRoleAssetsPanel({
        slot: "role.assets",
        id: pluginId,
        pluginId,
        Component: bindPluginClient(pluginId, roleAssets.component),
      });
    }
    if (roleMemory) {
      registry.registerRoleMemoryPanel({
        slot: "role.memory",
        id: pluginId,
        pluginId,
        Component: bindPluginClient(pluginId, roleMemory.component),
      });
    }
    if (navPage) {
      registry.registerNavPage({
        slot: "nav.page",
        id: pluginId,
        label: navPage.label,
        presentation: navPage.presentation,
        icon: navPage.icon,
        pluginId,
        Component: bindPluginClient(pluginId, navPage.component),
        Sidebar: navPage.sidebar ? bindPluginClient(pluginId, navPage.sidebar) : undefined,
        selectBlockedReason: navPage.selectBlockedReason ? () => navPage.selectBlockedReason!(desktopPluginHostServices) : undefined,
      });
    }
  }
}
