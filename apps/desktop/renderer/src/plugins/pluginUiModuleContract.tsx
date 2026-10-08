import type React from "react";
import { PluginHostServicesProvider, type PluginInjectedProps, type PluginUiModule } from "@yinfengwindy/shiori-sdk";
import { usePluginRpcClient } from "./usePluginRpcClient";
import { pluginHostServicesFor } from "./pluginHostServices";
import { pluginChatImageActionsRegistry, pluginRoleSettingsRegistry } from "./pluginFeatureRegistry";
import { createPluginSchemaSettingsSection } from "./pluginSchemaSettingsSectionFactory";
import { retiredPluginUiContribution } from "./runtimePluginUiValidation";
import { pluginUiRegistry } from "./pluginUiRegistry";

/** Narrows an unknown default export down to a well-formed PluginUiModule, without an unsafe cast. */
function isPluginUiModule(value: unknown): value is PluginUiModule {
  if (value === null || typeof value !== "object") return false;
  return "pluginId" in value && typeof value.pluginId === "string";
}

/**
 * Injects mount-scoped clients and the plugin's host services into
 * contributed components, both as the `host` prop and through the SDK's
 * `PluginHostServicesProvider` (the one context instance plugins read with
 * `usePluginHostServices`, #505).
 * Namespace binding expresses cooperation; it is not a same-realm sandbox.
 */
function bindPluginClient<TBaseProps extends object>(
  pluginId: string,
  Component: React.ComponentType<TBaseProps & PluginInjectedProps>,
): React.ComponentType<TBaseProps> {
  const host = pluginHostServicesFor(pluginId);
  return function PluginClientBoundComponent(props: TBaseProps) {
    const client = usePluginRpcClient(pluginId);
    return <PluginHostServicesProvider services={host}>
      <Component {...props} client={client} host={host} />
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
    const retired = retiredPluginUiContribution(uiModule);
    if (retired) {
      console.error(`[pluginUiModules] ${path}（${uiModule.pluginId}）已跳过：${retired}`);
      continue;
    }
    const { pluginId, settingsSection, navPage, roleAssets, accountDetail } = uiModule;
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
    if (accountDetail) {
      registry.registerAccountDetail({
        slot: "account.detail",
        pluginId,
        label: accountDetail.label,
        Icon: accountDetail.icon,
        Component: bindPluginClient(pluginId, accountDetail.component),
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
        selectBlockedReason: navPage.selectBlockedReason ? () => navPage.selectBlockedReason!(pluginHostServicesFor(pluginId)) : undefined,
      });
    }
  }
}
