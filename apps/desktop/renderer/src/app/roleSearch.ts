import { useEffect, useMemo, useRef, useState } from "react";
import type {
  RoleRecord,
  RoleSearchResult,
  SessionPayload,
  SessionSearchResult,
} from "../shared/types";

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

function roleForSearchResult(
  roles: readonly RoleRecord[],
  result: SessionSearchResult,
): RoleRecord | null {
  return roles.find((role) => result.session_key === `role:${role.id}`) ?? null;
}

/** Returns the stable persisted message id carried by the FTS result. */
export function resolveSearchResultMessageKey(messageId: string | null): string {
  return String(messageId ?? "").trim();
}

/** Combines local role-name matches with lightweight FTS message results. */
export function createRoleSearchResults(
  roles: readonly RoleRecord[],
  messageResults: readonly SessionSearchResult[],
  searchQuery: string,
): RoleSearchResult[] {
  const query = searchQuery.trim().toLowerCase();
  if (!query) return [];

  const roleResults = roles
    .filter((role) => role.name.toLowerCase().includes(query))
    .map((role) => ({
      roleId: role.id,
      roleName: role.name,
      roleAvatarAbs: role.avatar_abs,
      sessionKey: `role:${role.id}`,
      matchedMessageTimestamp: null,
      matchedMessageId: null,
      matchedMessageIndex: null,
      matchedMessagePreview: `角色 ${role.name}`,
      matchedField: "role" as const,
    }));
  const messageSearchResults = messageResults.flatMap((result) => {
    const role = roleForSearchResult(roles, result);
    if (!role || !result.id) return [];
    return [{
      roleId: role.id,
      roleName: role.name,
      roleAvatarAbs: role.avatar_abs,
      sessionKey: result.session_key,
      matchedMessageTimestamp: result.timestamp,
      matchedMessageId: result.id,
      matchedMessageIndex: null,
      matchedMessagePreview: result.preview,
      matchedField: "message" as const,
    }];
  });
  return [...roleResults, ...messageSearchResults].slice(0, 60);
}

function isSessionSearchResult(value: unknown): value is SessionSearchResult {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const result = value as Record<string, unknown>;
  return typeof result.id === "string"
    && typeof result.session_key === "string"
    && typeof result.seq === "number"
    && typeof result.role === "string"
    && typeof result.preview === "string"
    && (typeof result.timestamp === "string" || result.timestamp === null);
}

/** Extracts only valid FTS hits from a successful bridge response. */
export function parseRoleSearchMessageResults(payload: Record<string, unknown>): SessionSearchResult[] {
  return Array.isArray(payload.results)
    ? payload.results.filter(isSessionSearchResult)
    : [];
}

/** Treats bridge failures as an empty result set so prior-query hits cannot remain visible. */
export function resolveRoleSearchMessageResults(
  payload: Record<string, unknown>,
  error: unknown,
): SessionSearchResult[] {
  return error ? [] : parseRoleSearchMessageResults(payload);
}

/** Searches persisted desktop messages without loading each role's session into the renderer. */
export function useRoleSearch({
  roles,
  showSearchDialog,
  searchQuery,
}: UseRoleSearchArgs) {
  const [searchingSessions, setSearchingSessions] = useState(false);
  const [messageResults, setMessageResults] = useState<SessionSearchResult[]>([]);
  const requestGenerationRef = useRef(0);
  const normalizedQuery = searchQuery.trim();

  useEffect(() => {
    const requestGeneration = requestGenerationRef.current + 1;
    requestGenerationRef.current = requestGeneration;
    if (!showSearchDialog || !normalizedQuery) {
      setSearchingSessions(false);
      setMessageResults([]);
      return;
    }

    let cancelled = false;

    async function searchMessages(): Promise<void> {
      setMessageResults([]);
      setSearchingSessions(true);
      try {
        const res = await window.miraDesktop.invoke({
          method: "session.search",
          payload: { query: normalizedQuery, limit: 60 },
        });
        if (cancelled || requestGenerationRef.current !== requestGeneration) return;
        setMessageResults(resolveRoleSearchMessageResults(res.payload, res.error));
      } catch {
        if (!cancelled && requestGenerationRef.current === requestGeneration) {
          setMessageResults([]);
        }
      } finally {
        if (!cancelled) {
          setSearchingSessions(false);
        }
      }
    }

    void searchMessages();
    return () => {
      cancelled = true;
    };
  }, [normalizedQuery, showSearchDialog]);

  const searchResults = useMemo(
    () => createRoleSearchResults(roles, messageResults, searchQuery),
    [messageResults, roles, searchQuery],
  );

  function getMessageKey(_roleId: string, messageId: string | null, _messageIndex: number | null): string {
    return resolveSearchResultMessageKey(messageId);
  }

  return {
    searchingSessions,
    searchResults,
    getMessageKey,
  };
}
