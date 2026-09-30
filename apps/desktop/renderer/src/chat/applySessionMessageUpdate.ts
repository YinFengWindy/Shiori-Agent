import type { SessionMessage, SessionPayload, SessionSummary } from "@shiori/plugin-sdk";
import { mergeSessionSummaryAndMessage } from "../app/sessionMessagePagination";

/** Applies a plugin's message mutation only if the originating session is still open. */
export function applySessionMessageUpdate(current: SessionPayload | null, sessionKey: string, summary: SessionSummary, message: SessionMessage) {
  if (current?.key !== sessionKey || summary.key !== sessionKey) return current;
  return mergeSessionSummaryAndMessage(current, summary, message);
}
