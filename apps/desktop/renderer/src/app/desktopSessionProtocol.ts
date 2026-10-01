import { errorMessage, type SessionMessage, type SessionMessagePage, type SessionMessageUpdatePayload, type SessionPayload } from "@shiori/sdk";
import { isRecord } from "../shared/isRecord";
import { getSessionPaginationState, parseSessionMessagePage, parseSessionSummary } from "./sessionMessagePagination";

/** Parses the paginated bridge response into the renderer's loaded-message session shape. */
export function parseOpenedSessionPayload(payload: Record<string, unknown>): SessionPayload | null {
  const session = parseSessionSummary(payload.session);
  if (session && isRecord(payload.session) && Array.isArray(payload.session.messages)
    && payload.session.messages.every((message) => isRecord(message)
      && typeof message.role === "string" && typeof message.content === "string")) {
    return {
      ...session,
      messages: payload.session.messages,
    };
  }
  const page = parseSessionMessagePage(payload.page);
  if (!session || !page) {
    return null;
  }
  return {
    ...session,
    messages: page.messages,
    pagination: getSessionPaginationState(page),
  };
}

/** Parses a bridge event or mutation response carrying a summary and at most one changed message. */
export function parseSessionMessageUpdatePayload(
  payload: Record<string, unknown>,
): SessionMessageUpdatePayload | null {
  const session = parseSessionSummary(payload.session);
  const rawMessage = payload.message;
  if (!session || (rawMessage != null && (!isRecord(rawMessage)
    || typeof rawMessage.role !== "string" || typeof rawMessage.content !== "string"))) {
    return null;
  }
  const rawMessages = payload.messages;
  if (rawMessages != null && (!Array.isArray(rawMessages)
    || !rawMessages.every((item) => isRecord(item)
      && typeof item.role === "string" && typeof item.content === "string"))) {
    return null;
  }
  return {
    session,
    message: rawMessage as SessionMessage | null,
    messages: rawMessages as SessionMessage[] | undefined,
  };
}

/** Loads the authoritative role session without changing renderer state. */
export async function fetchRoleSession(roleId: string): Promise<{
  error: string | null;
  session: SessionPayload | null;
  page: SessionMessagePage | null;
}> {
  try {
    const res = await window.miraDesktop.invoke({
      method: "session.openByRole",
      payload: { role_id: roleId },
    });
    if (res.error) {
      return {
        error: errorMessage(res.error, { includeDetail: true }),
        session: null,
        page: null,
      };
    }
    const session = parseOpenedSessionPayload(res.payload);
    if (!session) {
      return {
        error: "打开角色会话响应无效",
        session: null,
        page: null,
      };
    }
    const page = parseSessionMessagePage(res.payload.page);
    return {
      error: page ? null : "打开角色会话分页响应无效",
      session: page ? session : null,
      page,
    };
  } catch (error) {
    return {
      error: errorMessage(error, { includeDetail: true }),
      session: null,
      page: null,
    };
  }
}
