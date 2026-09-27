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

/** Consequence text for the delete confirmation; empty when nothing is pending. */
export function accountDeletionDescription(account: AccountIdentity | null) {
  return account ? `“${accountHeadline(account)}” 的凭据和平台数据会被清除，历史消息保留。` : "";
}

/** Disabled providers cannot be shown online even if a stale live report remains. */
export function accountStatus(account: AccountSnapshot) {
  if (!account.pluginEnabled || !account.runtimeActive) return "离线";
  switch (account.connection) {
    case "online": return "在线";
    case "connecting": return "连接中";
    case "login_required": return "需要登录";
    case "error": return "故障";
    default: return "离线";
  }
}
