/**
 * Account snapshot and status vocabulary shared by the host's account pages
 * and the channel plugins' `account.detail` components (the snapshot arrives
 * as the `account` prop).
 */

/** Account-wide response policy the account's plugin saves with it; every group chat follows it. */
export type AccountResponseRules = {
  privateEnabled: boolean;
  groupEnabled: boolean;
  requireMention: boolean;
  blockedSenderIds: string[];
};

/** An account a loaded plugin registered, joined with its current plugin report. */
export type AccountSnapshot = {
  id: string;
  pluginId: string;
  platform: string;
  platformAccountId: string;
  configRef: string;
  displayName: string;
  /** The platform account's own picture as an image `data:` URI; `""` when unknown. */
  avatarUrl: string;
  roleId: string;
  runtimeActive: boolean;
  connection: "unknown" | "connecting" | "online" | "offline" | "login_required" | "error";
  /** `groups` means this account can receive group conversations; other capabilities remain plugin-defined. */
  capabilities: string[];
  error: string;
  responseRules: AccountResponseRules;
};

/** Status colors shared by status dots and the account status card. */
export type AccountStatusTone = "success" | "warning" | "danger" | "muted";

/** A status as shown to the user: its words and its dot color. */
export type AccountStatusView = { label: string; tone: AccountStatusTone };

/** Account commands whose request is in flight; their status shows at once, before any report. */
export type AccountPendingAction = "connect" | "disconnect" | "logout";

/** Whether the account is connected right now, as its plugin last reported. */
export function accountOnline(account: Pick<AccountSnapshot, "runtimeActive" | "connection"> | null) {
  return Boolean(account?.runtimeActive && account.connection === "online");
}
