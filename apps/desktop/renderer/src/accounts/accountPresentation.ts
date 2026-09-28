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

/** One platform offered when adding an account to a role. */
export type AccountPlatformChoice = { pluginId: string; label: string; bound: boolean };

/**
 * Platforms a role can add an account on. A role holds one account per plugin
 * (Feishu and Lark are one plugin), so a plugin it already has is `bound`.
 */
export function accountPlatformChoices(
  platforms: ReadonlyArray<{ pluginId: string; label: string }>,
  owned: ReadonlyArray<Pick<AccountSnapshot, "pluginId">>,
): AccountPlatformChoice[] {
  const bound = new Set(owned.map((account) => account.pluginId));
  return platforms.map(({ pluginId, label }) => ({ pluginId, label, bound: bound.has(pluginId) }));
}
