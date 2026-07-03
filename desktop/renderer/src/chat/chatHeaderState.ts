type ResolveChatHeaderTitleOptions = {
  activeRoleName: string | null;
  activeSessionKey: string;
  sendingSessions: Record<string, string>;
};

/** Resolves the visible chat header title without leaking one role's sending state into another role view. */
export function resolveChatHeaderTitle({
  activeRoleName,
  activeSessionKey,
  sendingSessions,
}: ResolveChatHeaderTitleOptions) {
  if (!activeRoleName) {
    return "选择一个角色";
  }
  return activeSessionKey && sendingSessions[activeSessionKey]
    ? "正在输入中..."
    : activeRoleName;
}
