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
