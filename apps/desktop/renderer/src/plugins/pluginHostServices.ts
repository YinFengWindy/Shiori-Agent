import type { ComponentProps, ComponentType } from "react";
import { AccountDetailActions } from "../accounts/AccountDetailActions";
import { AccountStatusCard, type AccountStatusCardProps } from "../accounts/AccountStatusCard";
import { invokeBridgePayload } from "../shared/bridgeInvoke";
import type { RoleRecord } from "../shared/types";
import { Reveal } from "../shared/ui/Reveal";
import { pluginHostFeedback, type PluginHostFeedback } from "./pluginHostFeedback";
import { HostConfirmDialog, HostInlineError, type HostConfirmDialogProps, type HostInlineErrorProps } from "./pluginHostUi";

/** Host components a plugin UI may render (runtime API 2.4.0; the account pieces serve `account.detail`). */
export type PluginHostUi = {
  /** The host's in-page error block; `persona` (true or a scene key) lets 吟风 front it. */
  InlineError: ComponentType<HostInlineErrorProps>;
  /** The host's confirmation dialog; `persona` (true or a scene key) lets 吟风 lead it. */
  ConfirmDialog: ComponentType<HostConfirmDialogProps>;
  /** The shared account connection card: status, the one connect/disconnect button, plugin rows below. */
  AccountStatusCard: ComponentType<AccountStatusCardProps>;
  /** A plugin's secondary account actions, shown in the account detail's danger zone next to 删除账号. */
  AccountDetailActions: ComponentType<ComponentProps<typeof AccountDetailActions>>;
  /** Fade + height show/hide for a block that comes and goes with state (QR code, progress). */
  Reveal: ComponentType<ComponentProps<typeof Reveal>>;
};

/** Narrow host services available to plugin UI without exposing raw IPC. */
export type PluginHostServices = {
  onEvent: typeof window.miraDesktop.onEvent;
  listRoles: () => Promise<RoleRecord[]>;
  pickImages: (options: { multiple: boolean }) => Promise<string[]>;
  /** Native user selection plus bounded private staging, without a media grant. */
  pickFiles: typeof window.miraDesktop.pickFiles;
  /** Toasts in the host queue; `persona` (true or a scene key) lets 吟风 front one (runtime API 2.4.0). */
  feedback: PluginHostFeedback;
  /** Host components (runtime API 2.4.0). */
  ui: PluginHostUi;
};

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
