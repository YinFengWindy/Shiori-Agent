import { getChatMessageReactKey } from "./chatMessageIdentity";
import { summarizeChatReplyContent } from "./chatComposerState";
import { normalizeSessionMediaPaths } from "./chatMedia";
import type { ChatSendRequest, SessionMessage } from "../shared/types";

/** Longest error text shown inline; anything longer (or multi-line) moves behind 「详情」. */
const inlineErrorMaxLength = 80;

/** Where a failed turn's user message sits and what re-sending it looks like. */
type FailedTurn = {
  errorKey: string;
  request: ChatSendRequest;
};

function findFailedTurn(messages: readonly SessionMessage[]): FailedTurn | null {
  const lastIndex = messages.length - 1;
  const last = messages[lastIndex];
  if (!last || last.role !== "error") return null;
  // The failed turn may have left a partial assistant trace between the user
  // message and the error row; the nearest user message is what was sent.
  for (let index = lastIndex - 1; index >= 0; index -= 1) {
    const message = messages[index]!;
    if (message.role === "error") return null;
    if (message.role !== "user") continue;
    const content = message.content.trim();
    const attachments = normalizeSessionMediaPaths(message.media);
    if (!content && !attachments.length) return null;
    const metadata = message.metadata ?? {};
    const replyContent = String(metadata.reply_to_content ?? "").trim();
    return {
      errorKey: getChatMessageReactKey(last, lastIndex),
      request: {
        content,
        attachments,
        replyTarget: replyContent
          ? {
              messageId: String(metadata.reply_to_message_id ?? "").trim(),
              content: replyContent,
              sender: String(metadata.reply_to_sender ?? "").trim(),
              preview: summarizeChatReplyContent(replyContent),
            }
          : null,
      },
    };
  }
  return null;
}

/**
 * Returns the render key of the error row that can be retried: only the
 * conversation's latest row, and only when a user message precedes it.
 * Older error rows describe turns the conversation has already moved past.
 */
export function findRetryableChatErrorKey(messages: readonly SessionMessage[]): string {
  return findFailedTurn(messages)?.errorKey ?? "";
}

/**
 * Builds the send request that retries the failed turn ending in `errorKey`:
 * the same text, attachments and quote as the user message that failed. The
 * retry goes through the normal send path, so the backend records it as a new
 * user message (single timeline — nothing is rewritten).
 */
export function buildChatRetryRequest(
  messages: readonly SessionMessage[],
  errorKey: string,
): ChatSendRequest | null {
  const failedTurn = findFailedTurn(messages);
  return failedTurn && failedTurn.errorKey === errorKey ? failedTurn.request : null;
}

/**
 * Splits an error row into what is always shown and an optional expandable
 * detail: short single-line messages show as-is; long or multi-line ones
 * (raw provider/transport errors) get a generic summary with the full text
 * behind 「详情」.
 */
export function splitChatErrorContent(content: string): { summary: string; detail: string } {
  const text = content.trim();
  if (!text) return { summary: "回复失败", detail: "" };
  if (text.length <= inlineErrorMaxLength && !text.includes("\n")) return { summary: text, detail: "" };
  return { summary: "回复失败", detail: text };
}
