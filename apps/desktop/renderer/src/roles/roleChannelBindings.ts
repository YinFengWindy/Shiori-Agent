import type { RoleChannelBinding } from "../shared/types";
import { desktopChannelName, findRoleChannel, type RoleChannelCatalog } from "./roleChannelCatalog";
import { composeRoleBindingChatId, defaultRoleChatType, findRoleChatType, roleBindingNumber } from "./roleChatTypes";

/** Supported directions for editing the proactive fallback order. */
export type RoleChannelBindingMoveDirection = "up" | "down";

/** Creates an editable channel binding for a role, typed as the channel's first declared session type. */
export function createRoleChannelBinding(roleId: string, channel: string, catalog: RoleChannelCatalog): RoleChannelBinding {
  return {
    channel,
    chat_id: channel === desktopChannelName ? `role:${roleId}` : "",
    chat_type: defaultRoleChatType(findRoleChannel(catalog, channel)),
    blocked_senders: [],
  };
}

/**
 * Changes a binding channel while preserving the desktop role-session
 * invariant. The session type resets to the new channel's first declared type;
 * an entered number is kept without the old type's prefix and re-prefixed for the new one.
 * The blacklist is dropped: its member IDs belong to the old channel.
 */
export function changeRoleBindingChannel(
  binding: RoleChannelBinding,
  channel: string,
  roleId: string,
  catalog: RoleChannelCatalog,
): RoleChannelBinding {
  const nextChannel = findRoleChannel(catalog, channel);
  const chatType = defaultRoleChatType(nextChannel);
  const number = binding.channel === desktopChannelName
    ? ""
    : roleBindingNumber(binding.chat_id, findRoleChatType(findRoleChannel(catalog, binding.channel), binding.chat_type));
  return {
    ...binding,
    channel,
    chat_id: channel === desktopChannelName
      ? `role:${roleId}`
      : composeRoleBindingChatId(number, findRoleChatType(nextChannel, chatType)),
    chat_type: chatType,
    blocked_senders: [],
  };
}

/** Identifies the role-owned desktop transport binding. */
export function isDesktopRoleBinding(binding: RoleChannelBinding): boolean {
  return binding.channel === desktopChannelName;
}

/** Moves a role binding without mutating the form's current binding array. */
export function moveRoleChannelBinding(
  bindings: RoleChannelBinding[],
  index: number,
  direction: RoleChannelBindingMoveDirection,
): RoleChannelBinding[] {
  const targetIndex = direction === "up" ? index - 1 : index + 1;
  if (index < 0 || index >= bindings.length || targetIndex < 0 || targetIndex >= bindings.length) {
    return bindings;
  }
  const nextBindings = [...bindings];
  [nextBindings[index], nextBindings[targetIndex]] = [nextBindings[targetIndex], nextBindings[index]];
  return nextBindings;
}

/** Orders usable proactive targets with the selected target first. */
export function buildProactiveTransportSequence(
  bindings: RoleChannelBinding[],
  preferredChannel: string,
  preferredChatId: string,
): RoleChannelBinding[] {
  const usableBindings = bindings.filter((binding) => binding.chat_id.trim());
  const preferredIndex = usableBindings.findIndex(
    (binding) => binding.channel === preferredChannel && binding.chat_id === preferredChatId,
  );
  if (preferredIndex <= 0) {
    return usableBindings;
  }
  return [
    usableBindings[preferredIndex],
    ...usableBindings.slice(0, preferredIndex),
    ...usableBindings.slice(preferredIndex + 1),
  ];
}
