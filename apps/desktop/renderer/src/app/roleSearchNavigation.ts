import type { RoleSearchResult } from "../shared/types";

type SearchNavigationOptions = {
  recordHistory?: boolean;
};

type NavigateToRoleSearchResultArgs = {
  result: RoleSearchResult;
  messageKey: string;
  openChatView: (options?: SearchNavigationOptions) => void;
  queueMessageNavigation: (roleId: string, messageKey: string) => void;
  clearMessageNavigation: () => void;
  openRole: (roleId: string, options?: SearchNavigationOptions) => Promise<boolean>;
  loadMessagesAround: (messageId: string, sessionKey: string) => Promise<boolean>;
};

/** Applies the navigation actions for one selected role or message search result. */
export async function navigateToRoleSearchResult({
  result,
  messageKey,
  openChatView,
  queueMessageNavigation,
  clearMessageNavigation,
  openRole,
  loadMessagesAround,
}: NavigateToRoleSearchResultArgs): Promise<void> {
  openChatView({ recordHistory: false });
  if (result.matchedField !== "message") {
    clearMessageNavigation();
    await openRole(result.roleId, { recordHistory: true });
    return;
  }
  clearMessageNavigation();
  if (!messageKey) return;
  const opened = await openRole(result.roleId, { recordHistory: true });
  if (!opened) return;
  const loaded = await loadMessagesAround(messageKey, result.sessionKey);
  if (loaded) {
    queueMessageNavigation(result.roleId, messageKey);
  }
}
