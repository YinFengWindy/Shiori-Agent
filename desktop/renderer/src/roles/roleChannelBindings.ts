import type { RoleChannelBinding } from "../shared/types";

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

/** Returns the channel-specific description for an inbound sender allow-list. */
export function roleBindingAllowFromLabel(channel: string): string {
  if (channel === "telegram") {
    return "允许对象（Telegram 用户 ID 或用户名，逗号分隔；留空允许全部）";
  }
  if (channel === "qq") {
    return "允许对象（QQ 号，逗号分隔；留空允许全部）";
  }
  return "允许对象（逗号分隔；留空允许全部）";
}
