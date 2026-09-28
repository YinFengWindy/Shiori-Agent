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
export function accountStatus(account: AccountSnapshot) {
  if (!account.runtimeActive) return "离线";
  switch (account.connection) {
    case "online": return "在线";
    case "connecting": return "连接中";
    case "login_required": return "需要登录";
    case "error": return "故障";
    default: return "离线";
  }
}
