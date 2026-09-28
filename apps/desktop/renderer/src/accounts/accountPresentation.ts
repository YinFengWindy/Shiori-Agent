import type { AccountSnapshot } from "./accountClient";

type AccountIdentity = Pick<AccountSnapshot, "platform" | "displayName" | "platformAccountId">;

/** Name shown for an account: its platform nickname, else the platform account ID. */
export function accountName(account: Pick<AccountSnapshot, "displayName" | "platformAccountId">) {
  return account.displayName || account.platformAccountId;
}

/** One-line identity used in lists and confirmations, e.g. `qq · 小栞`. */
export function accountHeadline(account: AccountIdentity) {
  return `${account.platform} · ${accountName(account)}`;
}

/**
 * Consequence text for deleting a role, naming the accounts deleted with it
 * (those of loaded plugins), or why they could not be listed.
 */
export function roleDeletionDescription(
  roleName: string,
  deleted: { accounts: ReadonlyArray<AccountIdentity>; error: string; status: "loading" | "ready" | "error" },
) {
  const base = `“${roleName}” 删除后会移除角色会话与相关素材。`;
  if (deleted.status === "loading") return `${base}正在读取关联账号...`;
  if (deleted.status === "error") return `${base}账号列表读取失败，暂不能确认删除范围。`;
  if (!deleted.accounts.length) return base;
  return `${base}以下账号会一并删除：${deleted.accounts.map(accountHeadline).join("、")}。`;
}

/** Consequence text for the delete confirmation; empty when nothing is pending. */
export function accountDeletionDescription(account: AccountIdentity | null) {
  return account ? `“${accountHeadline(account)}” 的凭据和平台数据会被清除，历史消息保留。` : "";
}

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

/** Status colors shared by status dots and the account status card. */
export type AccountStatusTone = "success" | "warning" | "danger" | "muted";

/** A status as shown to the user: its words and its dot color. */
export type AccountStatusView = { label: string; tone: AccountStatusTone };

/** Account commands whose request is in flight; their status shows at once, before any report. */
export type AccountPendingAction = "connect" | "disconnect" | "logout";

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

/** Whether the account is connected right now, as its plugin last reported. */
export function accountOnline(account: Pick<AccountSnapshot, "runtimeActive" | "connection"> | null) {
  return Boolean(account?.runtimeActive && account.connection === "online");
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

/** The line under an account's name: its channel and platform ID, e.g. `QQ · 10001`. */
export function accountChannelLine(channelLabel: string, account: Pick<AccountSnapshot, "platformAccountId">) {
  return `${channelLabel} · ${account.platformAccountId}`;
}
