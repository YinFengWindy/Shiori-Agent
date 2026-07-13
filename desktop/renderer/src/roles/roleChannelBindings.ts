import type { RoleChannelBinding } from "../shared/types";

/** Supported directions for editing the proactive fallback order. */
export type RoleChannelBindingMoveDirection = "up" | "down";

/** Creates an editable channel binding for a role. */
export function createRoleChannelBinding(roleId: string, channel = "telegram"): RoleChannelBinding {
  return {
    channel,
    chat_id: channel === "desktop" ? `role:${roleId}` : "",
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
    chat_id: channel === "desktop"
      ? `role:${roleId}`
      : binding.channel === "desktop"
        ? ""
        : binding.chat_id,
  };
}

/** Identifies the role-owned desktop transport binding. */
export function isDesktopRoleBinding(binding: RoleChannelBinding): boolean {
  return binding.channel === "desktop";
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

/** Returns the display label for a supported role transport. */
export function roleBindingChannelLabel(channel: string): string {
  if (channel === "telegram") return "Telegram";
  if (channel === "qq") return "QQ";
  if (channel === "qqbot") return "QQBot";
  if (channel === "desktop") return "桌面端";
  return channel;
}

/** Returns the channel-specific description for an inbound sender allow-list. */
export function roleBindingAllowFromLabel(channel: string): string {
  if (channel === "telegram") {
    return "允许对象（Telegram 用户 ID 或用户名，逗号分隔；留空允许全部）";
  }
  if (channel === "qq") {
    return "允许对象（QQ 号，逗号分隔；留空允许全部）";
  }
  if (channel === "qqbot") {
    return "允许对象（QQBot OpenID，逗号分隔；留空允许全部）";
  }
  return "允许对象（逗号分隔；留空允许全部）";
}
