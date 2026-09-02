import { useRef } from "react";
import type React from "react";
import { getRoleIdFromSession } from "./appState";
import {
  mergeSessionMessagePage,
  mergeSessionMessagesAround,
  parseSessionMessagePage,
  parseSessionMessagesAround,
  parseSessionSummary,
} from "./sessionMessagePagination";
import type { SessionPayload } from "../shared/types";

type UseDesktopSessionPaginationArgs = {
  activeRoleIdRef: React.MutableRefObject<string>;
  activeSessionRef: React.MutableRefObject<SessionPayload | null>;
  setError: React.Dispatch<React.SetStateAction<string>>;
  updateCommittedActiveSession: (
    updater: (current: SessionPayload | null) => SessionPayload | null,
  ) => void;
};

type DesktopSessionPaginationControllerArgs = {
  getActiveRoleId: () => string;
  getActiveSession: () => SessionPayload | null;
  setError: React.Dispatch<React.SetStateAction<string>>;
  updateCommittedActiveSession: (
    updater: (current: SessionPayload | null) => SessionPayload | null,
  ) => void;
  invoke: typeof window.miraDesktop.invoke;
  generationRef: React.MutableRefObject<Record<string, number>>;
  loadingOlderRef: React.MutableRefObject<Record<string, boolean>>;
};

/** Creates cursor actions that discard responses no longer belonging to the visible session generation. */
export function createDesktopSessionPaginationController({
  getActiveRoleId,
  getActiveSession,
  setError,
  updateCommittedActiveSession,
  invoke,
  generationRef,
  loadingOlderRef,
}: DesktopSessionPaginationControllerArgs) {
  function invalidateSessionPagination(sessionKey: string): void {
    if (!sessionKey) return;
    generationRef.current[sessionKey] = (generationRef.current[sessionKey] ?? 0) + 1;
  }

  function isCurrentGeneration(sessionKey: string, generation: number): boolean {
    return getActiveSession()?.key === sessionKey
      && (generationRef.current[sessionKey] ?? 0) === generation;
  }

  /** Loads the page immediately preceding the oldest persisted message currently in memory. */
  async function loadOlderMessages(sessionKey = getActiveSession()?.key ?? ""): Promise<boolean> {
    const current = getActiveSession();
    if (!current || current.key !== sessionKey) return false;
    const pagination = current.pagination;
    if (!pagination?.has_more || pagination.next_before_seq == null || loadingOlderRef.current[sessionKey]) {
      return false;
    }
    const generation = generationRef.current[sessionKey] ?? 0;
    loadingOlderRef.current[sessionKey] = true;
    try {
      const roleId = getRoleIdFromSession(current) || getActiveRoleId();
      const res = await invoke({
        method: "session.messagesPage",
        payload: {
          role_id: roleId,
          session_key: sessionKey,
          before_seq: pagination.next_before_seq,
          limit: pagination.limit,
        },
      });
      if (res.error) throw new Error(res.error.message);
      const page = parseSessionMessagePage(res.payload.page);
      const summary = parseSessionSummary(res.payload.session);
      if (!page || !summary || summary.key !== sessionKey) {
        throw new Error("历史消息分页响应无效");
      }
      if (!isCurrentGeneration(sessionKey, generation)) return false;
      updateCommittedActiveSession((latest) => (
        latest?.key === sessionKey ? mergeSessionMessagePage({ ...latest, ...summary }, page) : latest
      ));
      return true;
    } catch (error) {
      if (isCurrentGeneration(sessionKey, generation)) {
        setError(error instanceof Error ? error.message : String(error));
      }
      return false;
    } finally {
      delete loadingOlderRef.current[sessionKey];
    }
  }

  /** Loads a bounded persisted context before the DOM layer highlights a search result. */
  async function loadMessagesAround(
    messageId: string,
    expectedSessionKey = getActiveSession()?.key ?? "",
  ): Promise<boolean> {
    const normalizedMessageId = messageId.trim();
    if (!normalizedMessageId || !expectedSessionKey) return false;
    const generation = generationRef.current[expectedSessionKey] ?? 0;
    try {
      const res = await invoke({
        method: "session.messagesAround",
        payload: { message_id: normalizedMessageId, context: 8 },
      });
      if (res.error) throw new Error(res.error.message);
      const around = parseSessionMessagesAround(res.payload.around);
      if (!around || around.targetMessageId !== normalizedMessageId || around.sessionKey !== expectedSessionKey) {
        throw new Error("历史消息定位响应无效");
      }
      if (!isCurrentGeneration(expectedSessionKey, generation)) return false;
      updateCommittedActiveSession((latest) => (
        latest?.key === expectedSessionKey ? mergeSessionMessagesAround(latest, around) : latest
      ));
      return true;
    } catch (error) {
      if (isCurrentGeneration(expectedSessionKey, generation)) {
        setError(error instanceof Error ? error.message : String(error));
      }
      return false;
    }
  }

  return {
    invalidateSessionPagination,
    loadOlderMessages,
    loadMessagesAround,
  };
}

/** Owns cursor reads and discards responses that no longer belong to the visible session generation. */
export function useDesktopSessionPagination(args: UseDesktopSessionPaginationArgs) {
  const generationRef = useRef<Record<string, number>>({});
  const loadingOlderRef = useRef<Record<string, boolean>>({});

  return createDesktopSessionPaginationController({
    ...args,
    getActiveRoleId: () => args.activeRoleIdRef.current,
    getActiveSession: () => args.activeSessionRef.current,
    invoke: (request) => window.miraDesktop.invoke(request),
    generationRef,
    loadingOlderRef,
  });
}
