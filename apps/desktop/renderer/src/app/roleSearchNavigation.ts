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
};

/** Applies the navigation actions for one selected role or message search result. */
export function navigateToRoleSearchResult({
  result,
  messageKey,
  openChatView,
  queueMessageNavigation,
  clearMessageNavigation,
  openRole,
}: NavigateToRoleSearchResultArgs): void {
  openChatView({ recordHistory: false });
  if (result.matchedField === "message") {
    if (messageKey) {
      queueMessageNavigation(result.roleId, messageKey);
    }
  } else {
    clearMessageNavigation();
  }
  void openRole(result.roleId, { recordHistory: true });
}
