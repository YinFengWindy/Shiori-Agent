import type { PluginHostServices } from "@shiori/plugin-sdk";
import { AccountDetailActions } from "../accounts/AccountDetailActions";
import { AccountStatusCard } from "../accounts/AccountStatusCard";
import { invokeBridgePayload } from "../shared/bridgeInvoke";
import { toFileUrl } from "../shared/format";
import type { RoleRecord } from "../shared/types";
import { Reveal } from "../shared/ui/Reveal";
import { pluginHostFeedback } from "./pluginHostFeedback";
import { createPluginHostConfig } from "./pluginHostConfig";
import { HostConfirmDialog, HostInlineError } from "./pluginHostUi";

/** The host services contract is owned by `@shiori/plugin-sdk` (#440); re-exported for host callers. */
export type { PluginHostServices, PluginHostUi } from "@shiori/plugin-sdk";

/** The services every plugin shares; only `config` is bound to one plugin. */
const sharedPluginHostServices: Omit<PluginHostServices, "config"> = {
  onEvent: (listener) => window.miraDesktop.onEvent(listener),
  async listRoles() {
    const payload = await invokeBridgePayload<{ roles: RoleRecord[] }>(window.miraDesktop.invoke, "roles.list", {});
    return payload.roles;
  },
  pickImages: (options) => window.miraDesktop.pickImages(options),
  pickFiles: (options) => window.miraDesktop.pickFiles(options),
  feedback: pluginHostFeedback,
  ui: {
    InlineError: HostInlineError, ConfirmDialog: HostConfirmDialog,
    AccountStatusCard, AccountDetailActions, Reveal,
  },
  // The host's own image resolver, so a plugin's image shows exactly as the host's would.
  assets: { url: (path) => toFileUrl(path) },
};

const boundPluginHostServices = new Map<string, PluginHostServices>();

/**
 * The host services injected into one plugin's contributions (its `host`
 * prop and `usePluginHostServices()`): one stable object per plugin, so its
 * config saves share one queue across all its mounted components.
 */
export function pluginHostServicesFor(pluginId: string): PluginHostServices {
  let services = boundPluginHostServices.get(pluginId);
  if (!services) {
    services = { ...sharedPluginHostServices, config: createPluginHostConfig(pluginId) };
    boundPluginHostServices.set(pluginId, services);
  }
  return services;
}
