import type { ComponentType } from "react";
import type { AccountSnapshot } from "../accounts/accountClient";
import { accountOnline } from "../accounts/accountPresentation";
import { prettifyPluginId } from "../plugins/pluginPresentation";
import { extractChatPreviewText } from "../roles/roleChatPreview";
import type { PhoneConversation } from "./phoneClient";

/** One app on the phone's home screen: an account of the role. */
export type PhoneApp = {
  accountId: string;
  /** The channel name its plugin registered for account controls (as on the role page's 账号 tab). */
  label: string;
  /** The channel's registered account mark; absent while its plugin's UI is not loaded. */
  Icon?: ComponentType<{ className?: string }>;
  /** Not connected right now (stopped plugin, disconnected, login needed, failing). */
  offline: boolean;
};

/** What the phone needs from the plugin UI registry about one plugin's account controls. */
export type PhoneAppChannel = { label: string; Icon?: ComponentType<{ className?: string }> };

/**
 * The home screen: one app per account of `roleId`, in the order the host
 * lists them. Every listed account shows, connected or not (a disabled
 * plugin's accounts are not listed at all, #473). `channelOf` gives the
 * plugin's registered channel label, the one the role page shows; a plugin
 * whose renderer UI registered none gets its word-cased id, never the raw one.
 */
export function phoneApps(
  accounts: readonly AccountSnapshot[],
  roleId: string,
  channelOf: (pluginId: string) => PhoneAppChannel | undefined,
): PhoneApp[] {
  return accounts
    .filter((account) => account.roleId === roleId)
    .map((account) => {
      const channel = channelOf(account.pluginId);
      return {
        accountId: account.id,
        label: channel?.label ?? prettifyPluginId(account.pluginId),
        Icon: channel?.Icon,
        offline: !accountOnline(account),
      };
    });
}

/** The conversations an app lists: those its account carries, keeping the bridge's newest-first order. */
export function accountConversations(conversations: readonly PhoneConversation[], accountId: string) {
  return conversations.filter((conversation) => conversation.accountId === accountId);
}

/**
 * A conversation row's second line: the newest message flattened to one
 * line (「[图片]」 for a picture alone). In a group, what someone else said
 * is prefixed with their name; the role's own messages carry no prefix.
 */
export function phoneConversationPreview({ chatType, lastMessage }: PhoneConversation) {
  const body = extractChatPreviewText(lastMessage.content) || (lastMessage.hasMedia ? "[图片]" : "");
  if (chatType === "group" && lastMessage.role === "user" && lastMessage.senderName) {
    return `${lastMessage.senderName}：${body}`;
  }
  return body;
}

/** The status bar's clock: local 24-hour 「HH:MM」. */
export function phoneStatusTime(now: Date) {
  return `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
}
