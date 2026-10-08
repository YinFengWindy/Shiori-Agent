/** Session messages as the desktop bridge returns them (chat image actions receive session updates). */
import type { AffectionSummary, LonelinessRuntime, RelationshipSnapshot } from "./role";

/** Single message in a role-bound session. */
export type SessionMessage = {
  id?: string;
  /** Stable persisted ordering cursor assigned by the session store. */
  seq?: number;
  /** Stable renderer-only identity used to keep one visual message node mounted across local and bridge updates. */
  render_id?: string;
  role: string;
  content: string;
  timestamp?: string;
  reasoning_content?: string | null;
  streaming?: boolean;
  tool_chain?: ChatToolCallGroup[];
  media?: string[];
  metadata?: Record<string, unknown>;
};

/** Sanitized tool call record displayed inside one assistant reply. */
export type ChatToolCall = {
  call_id: string;
  name: string;
  status: "running" | "success" | "error" | string;
  arguments: Record<string, unknown>;
  final_arguments: Record<string, unknown>;
  result: string;
};

/** One model iteration containing one or more tool calls. */
export type ChatToolCallGroup = {
  text: string;
  reasoning_content: string;
  calls: ChatToolCall[];
};

/** Session payload returned by the desktop bridge. */
export type SessionPayload = {
  key: string;
  created_at: string;
  updated_at: string;
  last_consolidated: number;
  metadata: Record<string, unknown> & {
    /** Formal state committed with the latest successful role reply. */
    current_mood?: string;
    current_thought?: string;
    relationship_snapshot?: RelationshipSnapshot | null;
    loneliness_runtime?: LonelinessRuntime | null;
    /** Absent until the role's first conversation initializes affection. */
    affection?: AffectionSummary | null;
  };
  messages: SessionMessage[];
  /** Present for sessions opened through the paginated desktop bridge contract. */
  pagination?: SessionPaginationState;
};

/** Session fields sent by the bridge when message history is intentionally omitted. */
export type SessionSummary = Omit<SessionPayload, "messages" | "pagination">;

/** One bounded group of persisted session messages. */
export type SessionMessagePage = {
  messages: SessionMessage[];
  limit: number;
  has_more: boolean;
  oldest_seq: number | null;
  newest_seq: number | null;
  total_count: number;
  before_seq: number | null;
  next_before_seq: number | null;
};

/** Renderer-owned cursor metadata for the messages currently loaded in one session. */
export type SessionPaginationState = Omit<SessionMessagePage, "messages">;

/** Summary plus changed messages used by incremental bridge responses and events. */
export type SessionMessageUpdatePayload = {
  session: SessionSummary;
  message: SessionMessage | null;
  /** Contains every persisted message appended by one external turn when available. */
  messages?: SessionMessage[];
};

/** One image in a chat session's image history, addressed by its message and media slot. */
export type ChatImageHistoryEntry = {
  historyKey: string;
  path: string;
  messageId: string;
  mediaIndex: number;
  timestamp: string | null;
};
