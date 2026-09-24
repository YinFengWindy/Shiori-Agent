import { getChatMessageReactKey } from "./chatMessageIdentity";
import type { SessionMessage } from "../shared/types";

/** Longest error text shown inline when no separate detail exists; longer or multi-line text moves behind 「详情」. */
const inlineErrorMaxLength = 80;

/** The latest failed turn: its error row and the persisted user message the backend re-runs. */
export type ChatRetryTarget = {
  errorKey: string;
  userMessageId: string;
};

function findFailedTurn(messages: readonly SessionMessage[]): ChatRetryTarget | null {
  const lastIndex = messages.length - 1;
  const last = messages[lastIndex];
  if (!last || last.role !== "error") return null;
  // The failed turn may have left a transient assistant trace between the
  // user message and the error row; the nearest user message is what was sent.
  for (let index = lastIndex - 1; index >= 0; index -= 1) {
    const message = messages[index]!;
    if (message.role === "error") return null;
    if (message.role !== "user") continue;
    // Only a persisted message (it has a bridge id) can be re-run in place.
    const userMessageId = String(message.id ?? "").trim();
    if (!userMessageId) return null;
    return { errorKey: getChatMessageReactKey(last, lastIndex), userMessageId };
  }
  return null;
}

/**
 * Returns the render key of the error row that can be retried: only the
 * conversation's latest row, and only when a persisted user message precedes
 * it. Older error rows describe turns the conversation has already moved past.
 */
export function findRetryableChatErrorKey(messages: readonly SessionMessage[]): string {
  return findFailedTurn(messages)?.errorKey ?? "";
}

/**
 * Resolves what `chat.retry` needs to re-run the failed turn ending in
 * `errorKey`: the id of its persisted user message. The backend reuses that
 * message, so the single timeline gets no duplicate user message.
 */
export function findChatRetryTarget(
  messages: readonly SessionMessage[],
  errorKey: string,
): ChatRetryTarget | null {
  const failedTurn = findFailedTurn(messages);
  return failedTurn && failedTurn.errorKey === errorKey ? failedTurn : null;
}

/**
 * Splits an error row into what is always shown and an optional expandable
 * detail. A cause reported by the bridge (`detail`) goes behind 「详情」 under
 * the message; without one, short single-line messages show as-is and long
 * or multi-line ones (raw transport errors) get a generic summary.
 */
export function splitChatErrorContent(content: string, detail = ""): { summary: string; detail: string } {
  const text = content.trim();
  const reportedDetail = detail.trim();
  if (reportedDetail) return { summary: text || "回复失败", detail: reportedDetail };
  if (!text) return { summary: "回复失败", detail: "" };
  if (text.length <= inlineErrorMaxLength && !text.includes("\n")) return { summary: text, detail: "" };
  return { summary: "回复失败", detail: text };
}
