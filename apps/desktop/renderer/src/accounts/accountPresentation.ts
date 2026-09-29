import type { AccountSnapshot } from "@shiori/plugin-sdk";
import { prettifyPluginId } from "../plugins/pluginPresentation";

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

/**
 * The name of an account's channel: the label its plugin registered for
 * account controls (「QQ」, 「飞书 / Lark」), or, when the plugin's UI
 * registered none, its word-cased id (never the raw one).
 */
export function accountChannelLabel(pluginId: string, registered: { label: string } | undefined) {
  return registered?.label ?? prettifyPluginId(pluginId);
}

/** The line under an account's name: its channel and platform ID, e.g. `QQ · 10001`. */
export function accountChannelLine(channelLabel: string, account: Pick<AccountSnapshot, "platformAccountId">) {
  return `${channelLabel} · ${account.platformAccountId}`;
}
