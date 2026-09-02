import type { RoleSearchResult } from "../shared/types";

type SearchNavigationOptions = {
  recordHistory?: boolean;
};

type SearchRoleOpenOptions = SearchNavigationOptions & {
  preserveCurrentSession?: boolean;
};

type MessageNavigationTarget = {
  roleId: string;
  messageKey: string;
};

type NavigateToRoleSearchResultArgs = {
  result: RoleSearchResult;
  messageKey: string;
  openChatView: (options?: SearchNavigationOptions) => void;
  isSearchResultSessionActive: (roleId: string, sessionKey: string) => boolean;
  queueMessageNavigation: (roleId: string, messageKey: string) => void;
  clearMessageNavigation: (target?: MessageNavigationTarget) => void;
  openRole: (roleId: string, options?: SearchRoleOpenOptions) => Promise<boolean>;
  loadMessagesAround: (messageId: string, sessionKey: string) => Promise<boolean>;
};

/** Applies the navigation actions for one selected role or message search result. */
export async function navigateToRoleSearchResult({
  result,
  messageKey,
  openChatView,
  isSearchResultSessionActive,
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
  queueMessageNavigation(result.roleId, messageKey);
  const opened = isSearchResultSessionActive(result.roleId, result.sessionKey)
    || await openRole(result.roleId, { recordHistory: true, preserveCurrentSession: true });
  if (!opened) {
    clearMessageNavigation({ roleId: result.roleId, messageKey });
    return;
  }
  const loaded = await loadMessagesAround(messageKey, result.sessionKey);
  if (!loaded) {
    clearMessageNavigation({ roleId: result.roleId, messageKey });
  }
}
