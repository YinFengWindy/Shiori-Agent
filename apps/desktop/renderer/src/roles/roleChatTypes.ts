import type { ChannelChatTypeDeclaration, ChannelSummary } from "../plugins/pluginBridgeClient";
import type { RoleChannelBinding, RoleChatType } from "../shared/types";
import { findRoleChannel, roleChannelLabel, type RoleChannelCatalog } from "./roleChannelCatalog";

/** Finds the declared session type a binding selected; null when the channel declares none (or not this one). */
export function findRoleChatType(channel: ChannelSummary | null, chatType: RoleChatType) {
  return channel?.chatTypes.find((item) => item.type === chatType) ?? null;
}

/** Session type of a new binding on this channel: its first declared type, else private. */
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
 * The stored chat id for a typed number: the selected type's prefix plus the
 * trimmed number. An empty number stays empty so a bare prefix is never saved.
 */
export function composeRoleBindingChatId(number: string, chatType: ChannelChatTypeDeclaration | null) {
  const prefix = chatType?.prefix;
  if (!prefix) return number;
  const trimmed = number.trim();
  return trimmed ? `${prefix}${trimmed}` : "";
}

/**
 * Switches a binding to another session type, keeping the entered number but
 * re-deriving the prefix, so e.g. `gqq:` never carries into a private chat.
 */
export function changeRoleBindingChatType(binding: RoleChannelBinding, channel: ChannelSummary | null, chatType: RoleChatType) {
  const number = roleBindingNumber(binding.chat_id, findRoleChatType(channel, binding.chat_type));
  return { ...binding, chat_type: chatType, chat_id: composeRoleBindingChatId(number, findRoleChatType(channel, chatType)) };
}

/** Label of one binding in pickers, e.g. "QQ（NapCat） · 群聊 831907794"; undeclared types show the raw chat id. */
export function roleBindingDisplayLabel(binding: RoleChannelBinding, catalog: RoleChannelCatalog) {
  const channelLabel = roleChannelLabel(binding.channel, catalog);
  const chatType = findRoleChatType(findRoleChannel(catalog, binding.channel), binding.chat_type);
  return chatType
    ? `${channelLabel} · ${chatType.label} ${roleBindingNumber(binding.chat_id, chatType)}`
    : `${channelLabel} · ${binding.chat_id}`;
}
