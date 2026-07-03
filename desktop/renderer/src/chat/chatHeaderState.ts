type ResolveChatHeaderTitleOptions = {
  activeRoleId: string;
  activeRoleName: string | null;
  sending: boolean;
  sendingRoleId: string;
};

/** Resolves the visible chat header title without leaking one role's sending state into another role view. */
export function resolveChatHeaderTitle({
  activeRoleId,
  activeRoleName,
  sending,
  sendingRoleId,
}: ResolveChatHeaderTitleOptions) {
  if (!activeRoleName) {
    return "选择一个角色";
  }
  return sending && activeRoleId !== "" && sendingRoleId === activeRoleId
    ? "正在输入中..."
    : activeRoleName;
}
