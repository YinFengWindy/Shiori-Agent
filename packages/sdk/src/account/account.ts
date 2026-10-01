/**
 * Account snapshot and status vocabulary shared by the host's account pages
 * and the channel plugins' `account.detail` components (the snapshot arrives
 * as the `account` prop).
 */

/**
 * Account-wide response policy the account's plugin saves with it; every group
 * chat follows it, and within a group the role only speaks when @-mentioned or
 * replied to.
 */
export type AccountResponseRules = {
  privateEnabled: boolean;
  groupEnabled: boolean;
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

/*
 * The host's own status wording, used by its account list and status card and
 * by the testing entry's stand-in card. Host-only (`@shiori/sdk/host-internal`):
 * plugins get it rendered through `host.ui.AccountStatusCard`, never as text.
 */

/** An account its plugin is not running cannot be shown online. */
export function accountStatus(account: Pick<AccountSnapshot, "runtimeActive" | "connection">) {
  if (!account.runtimeActive) return "离线";
  switch (account.connection) {
    case "online": return "在线";
    case "connecting": return "连接中";
    case "login_required": return "需要登录";
    case "error": return "故障";
    default: return "离线";
  }
}

const connectionTones: Record<AccountSnapshot["connection"], AccountStatusTone> = {
  online: "success",
  connecting: "warning",
  login_required: "warning",
  error: "danger",
  offline: "muted",
  unknown: "muted",
};

/** The host's reading of an account's live report; a stopped plugin reads as offline. */
export function accountStatusView(account: Pick<AccountSnapshot, "runtimeActive" | "connection">): AccountStatusView {
  return {
    label: accountStatus(account),
    tone: connectionTones[account.runtimeActive ? account.connection : "offline"] ?? "muted",
  };
}

const pendingLabels: Record<AccountPendingAction, string> = {
  connect: "正在连接",
  disconnect: "正在断开",
  logout: "正在退出",
};

/** Status shown while a connect, disconnect or logout request is still in flight. */
export function pendingAccountStatus(action: AccountPendingAction): AccountStatusView {
  return { label: pendingLabels[action], tone: "warning" };
}

/** Labels of the account status card's one button. */
export const accountCardActionLabels: Record<"connect" | "disconnect", string> = { connect: "连接", disconnect: "断开连接" };

/**
 * What the account status card shows: a request in flight first, then the
 * plugin's own status, then the host's reading of the account; and the
 * account's failure report while no request is in flight.
 */
export function accountCardView({ account, status, pending }: {
  account: AccountSnapshot | null;
  status?: AccountStatusView;
  pending: AccountPendingAction | null;
}): { status: AccountStatusView; failure: string } {
  const shown = pending ? pendingAccountStatus(pending) : status ?? (account ? accountStatusView(account) : { label: "未连接", tone: "muted" as const });
  return { status: shown, failure: !pending && account?.connection === "error" ? account.error : "" };
}
