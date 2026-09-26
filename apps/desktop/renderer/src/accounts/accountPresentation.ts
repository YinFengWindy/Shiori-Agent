import type { AccountSnapshot } from "./accountClient";

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
