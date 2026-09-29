import type { PluginHostServices } from "@shiori/plugin-sdk";
import { AccountDetailActions } from "../accounts/AccountDetailActions";
import { AccountStatusCard } from "../accounts/AccountStatusCard";
import { invokeBridgePayload } from "../shared/bridgeInvoke";
import type { RoleRecord } from "../shared/types";
import { Reveal } from "../shared/ui/Reveal";
import { pluginHostFeedback } from "./pluginHostFeedback";
import { HostConfirmDialog, HostInlineError } from "./pluginHostUi";

/** The host services contract is owned by `@shiori/plugin-sdk` (#440); re-exported for host callers. */
export type { PluginHostServices, PluginHostUi } from "@shiori/plugin-sdk";

/** Stable adapter supplied by the desktop composition boundary. */
export const desktopPluginHostServices: PluginHostServices = {
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
};
