import type { RoleChannelBinding } from "../shared/types";
import { desktopChannelName } from "./roleChannelCatalog";

/** Supported directions for editing the proactive fallback order. */
export type RoleChannelBindingMoveDirection = "up" | "down";

/** Creates an editable channel binding for a role. */
export function createRoleChannelBinding(roleId: string, channel: string): RoleChannelBinding {
  return {
    channel,
    chat_id: channel === desktopChannelName ? `role:${roleId}` : "",
    allow_from: [],
  };
}

/** Changes a binding channel while preserving the desktop role-session invariant. */
export function changeRoleBindingChannel(
  binding: RoleChannelBinding,
  channel: string,
  roleId: string,
): RoleChannelBinding {
  return {
    ...binding,
    channel,
    chat_id: channel === desktopChannelName
      ? `role:${roleId}`
      : binding.channel === desktopChannelName
        ? ""
        : binding.chat_id,
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
