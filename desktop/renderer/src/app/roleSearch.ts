import { useEffect, useMemo, useRef, useState } from "react";
import type { SearchableSessionRecord } from "./appState";
import type { RoleRecord, RoleSearchResult, SessionPayload } from "../shared/types";

type FetchRoleSession = (roleId: string) => Promise<{
  error: string | null;
  session: SessionPayload | null;
}>;

type UseRoleSearchArgs = {
  roles: RoleRecord[];
  showSearchDialog: boolean;
  searchQuery: string;
  activeRoleId: string;
  activeSession: SessionPayload | null;
  fetchRoleSession: FetchRoleSession;
  cacheRoleSession: (roleId: string, session: SessionPayload) => void;
};

type ResolveSearchResultMessageKeyArgs = {
  roleId: string;
  messageId: string | null;
  messageIndex: number | null;
  activeRoleId: string;
  activeSession: SessionPayload | null;
  searchIndex: SearchableSessionRecord[];
};

function truncateSearchPreview(value: string, query: string): string {
  const compactValue = value.replace(/\s+/g, " ").trim();
  if (!compactValue) return "空消息";
  const compactQuery = query.trim().toLowerCase();
  if (!compactQuery) return compactValue.slice(0, 88);
  const hitIndex = compactValue.toLowerCase().indexOf(compactQuery);
  if (hitIndex < 0) return compactValue.slice(0, 88);
  const start = Math.max(0, hitIndex - 16);
  const end = Math.min(compactValue.length, hitIndex + compactQuery.length + 44);
  const prefix = start > 0 ? "..." : "";
  const suffix = end < compactValue.length ? "..." : "";
  return `${prefix}${compactValue.slice(start, end)}${suffix}`;
}

/** Resolves the DOM message key for a selected search result. */
export function resolveSearchResultMessageKey({
  roleId,
  messageId,
  messageIndex,
  activeRoleId,
  activeSession,
  searchIndex,
}: ResolveSearchResultMessageKeyArgs): string {
  if (messageId) return String(messageId);
  if (messageIndex == null) return "";
  const indexedSession = searchIndex.find((item) => item.roleId === roleId)?.session ?? null;
  const indexedMessage = indexedSession?.messages[messageIndex] ?? null;
  const activeMessage = activeRoleId === roleId ? activeSession?.messages[messageIndex] ?? null : null;
  const message = indexedMessage ?? activeMessage;
  if (!message) return "";
  return String(message.id ?? `${message.role}-${messageIndex}`);
}

/** Builds desktop role search results from the current role sessions. */
export function createRoleSearchResults(
  searchIndex: SearchableSessionRecord[],
  searchQuery: string,
): RoleSearchResult[] {
  const query = searchQuery.trim().toLowerCase();
  if (!query) return [];

  const results: RoleSearchResult[] = [];
  for (const record of searchIndex) {
    if (record.roleName.toLowerCase().includes(query)) {
      results.push({
        roleId: record.roleId,
        roleName: record.roleName,
        roleAvatarAbs: record.roleAvatarAbs,
        sessionKey: record.session.key,
        matchedMessageTimestamp: record.session.updated_at ?? null,
        matchedMessageId: null,
        matchedMessageIndex: null,
        matchedMessagePreview: `角色 ${record.roleName}`,
        matchedField: "role",
      });
    }

    record.session.messages.forEach((message, messageIndex) => {
      const content = message.content.trim();
      if (!content) return;
      if (!content.toLowerCase().includes(query)) return;
      results.push({
        roleId: record.roleId,
        roleName: record.roleName,
        roleAvatarAbs: record.roleAvatarAbs,
        sessionKey: record.session.key,
        matchedMessageTimestamp: message.timestamp ?? null,
        matchedMessageId: message.id ?? null,
        matchedMessageIndex: messageIndex,
        matchedMessagePreview: truncateSearchPreview(content, query),
        matchedField: "message",
      });
    });
  }

  return results.slice(0, 60);
}

/** Manages the desktop role-search index and result projection. */
export function useRoleSearch({
  roles,
  showSearchDialog,
  searchQuery,
  activeRoleId,
  activeSession,
  fetchRoleSession,
  cacheRoleSession,
}: UseRoleSearchArgs) {
  const [searchingSessions, setSearchingSessions] = useState(false);
  const [searchIndex, setSearchIndex] = useState<SearchableSessionRecord[]>([]);
  const fetchRoleSessionRef = useRef(fetchRoleSession);
  const cacheRoleSessionRef = useRef(cacheRoleSession);

  useEffect(() => {
    fetchRoleSessionRef.current = fetchRoleSession;
    cacheRoleSessionRef.current = cacheRoleSession;
  }, [fetchRoleSession, cacheRoleSession]);

  useEffect(() => {
    if (!showSearchDialog) return;

    let cancelled = false;

    async function buildSearchIndex(): Promise<void> {
      if (!roles.length) {
        setSearchIndex([]);
        return;
      }
      setSearchingSessions(true);
      try {
        const sessionRecords = await Promise.all(
          roles.map(async (role) => {
            const { session } = await fetchRoleSessionRef.current(role.id);
            if (!session || cancelled) return null;
            cacheRoleSessionRef.current(role.id, session);
            return {
              roleId: role.id,
              roleName: role.name,
              roleAvatarAbs: role.avatar_abs,
              session,
            } satisfies SearchableSessionRecord;
          }),
        );
        if (cancelled) return;
        setSearchIndex(sessionRecords.filter((item): item is SearchableSessionRecord => item !== null));
      } finally {
        if (!cancelled) {
          setSearchingSessions(false);
        }
      }
    }

    void buildSearchIndex();

    return () => {
      cancelled = true;
    };
  }, [roles, showSearchDialog]);

  const searchResults = useMemo(
    () => createRoleSearchResults(searchIndex, searchQuery),
    [searchIndex, searchQuery],
  );

  function getMessageKey(roleId: string, messageId: string | null, messageIndex: number | null): string {
    return resolveSearchResultMessageKey({
      roleId,
      messageId,
      messageIndex,
      activeRoleId,
      activeSession,
      searchIndex,
    });
  }

  return {
    searchingSessions,
    searchResults,
    getMessageKey,
  };
}
