import type { ChannelChatTypeDeclaration, ChannelSummary } from "../plugins/pluginBridgeClient";
import type { RoleChannelBinding, RoleChatType } from "../shared/types";
import { desktopChannelName, findRoleChannel, roleChannelLabel, type RoleChannelCatalog } from "./roleChannelCatalog";

/** Whether a session type is a group chat: only group bindings carry a blacklist. */
export function isGroupChatType(chatType: RoleChatType) {
  return chatType === "group";
}

/** Finds the declared session type a binding selected; null when the channel declares none (or not this one). */
export function findRoleChatType(channel: ChannelSummary | null, chatType: RoleChatType) {
  return channel?.chatTypes.find((item) => item.type === chatType) ?? null;
}

/** Number copy of a binding without a declared type: the desktop session, or a read-only binding whose plugin is gone. */
const undeclaredChatIdLabel = "会话 ID";

/**
 * Field copy for a binding's number: the selected session type's declared copy;
 * without a declaration (desktop, or a read-only binding) a plain label.
 */
export function roleBindingChatIdCopy(chatType: ChannelChatTypeDeclaration | null) {
  return chatType
    ? { label: chatType.chatIdLabel, placeholder: chatType.chatIdHint ?? "" }
    : { label: undeclaredChatIdLabel, placeholder: "" };
}

/** Fallback names when no declaration is available for a stored binding. */
const storedChatTypeLabels: Record<RoleChatType, string> = { private: "私聊", group: "群聊" };

/** Display name of a binding's session type: the declared label, else the generic name of the stored type. */
export function roleChatTypeLabel(channel: ChannelSummary | null, chatType: RoleChatType) {
  return findRoleChatType(channel, chatType)?.label ?? storedChatTypeLabels[chatType];
}

/** Session type of a new binding on this channel: its first declared type; desktop (no declaration) is private. */
export function defaultRoleChatType(channel: ChannelSummary | null) {
  return channel?.chatTypes[0]?.type ?? "private";
}

/** Options for the type picker of a channel that declares session types. */
export function roleChatTypeOptions(channel: ChannelSummary) {
  return channel.chatTypes.map((item) => ({ value: item.type, label: item.label }));
}

/** The number the form shows: the stored chat id without the selected type's prefix. */
export function roleBindingNumber(chatId: string, chatType: ChannelChatTypeDeclaration | null) {
  const prefix = chatType?.prefix;
  return prefix && chatId.startsWith(prefix) ? chatId.slice(prefix.length) : chatId;
}

/**
 * The stored chat id for a typed number: the trimmed number behind the
 * selected type's prefix. A pasted internal id that already carries the prefix
 * (`gqq:123`) is not prefixed twice, and an empty number stays empty so a bare
 * prefix is never saved.
 */
export function composeRoleBindingChatId(number: string, chatType: ChannelChatTypeDeclaration | null) {
  const prefix = chatType?.prefix;
  const trimmed = number.trim();
  if (!prefix) return trimmed;
  const bare = roleBindingNumber(trimmed, chatType).trim();
  return bare ? `${prefix}${bare}` : "";
}

/**
 * Switches a binding to another session type, keeping the entered number but
 * re-deriving the prefix, so e.g. `gqq:` never carries into a private chat.
 * Only group bindings keep a blacklist; a private chat's partner is the chat itself.
 */
export function changeRoleBindingChatType(binding: RoleChannelBinding, channel: ChannelSummary | null, chatType: RoleChatType) {
  const number = roleBindingNumber(binding.chat_id, findRoleChatType(channel, binding.chat_type));
  return {
    ...binding,
    chat_type: chatType,
    chat_id: composeRoleBindingChatId(number, findRoleChatType(channel, chatType)),
    blocked_senders: isGroupChatType(chatType) ? binding.blocked_senders : [],
  };
}

/**
 * Label of one binding in lists, e.g. "QQ（NapCat） · 群聊 831907794"; undeclared
 * types show the raw chat id. The desktop session is just "桌面端": a role has
 * only one, and its chat id is internal.
 */
export function roleBindingDisplayLabel(binding: RoleChannelBinding, catalog: RoleChannelCatalog) {
  const channelLabel = roleChannelLabel(binding.channel, catalog);
  if (binding.channel === desktopChannelName) return channelLabel;
  const chatType = findRoleChatType(findRoleChannel(catalog, binding.channel), binding.chat_type);
  return chatType
    ? `${channelLabel} · ${chatType.label} ${roleBindingNumber(binding.chat_id, chatType)}`
    : `${channelLabel} · ${binding.chat_id}`;
}
