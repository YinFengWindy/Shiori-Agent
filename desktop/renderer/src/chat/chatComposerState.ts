import { ensureChatMessageRenderId } from "./chatMessageIdentity";
import type { ChatReplyTarget, SessionMessage } from "../shared/types";

/** Normalizes pending attachment paths so chat send logic can deduplicate repeated selections. */
export function normalizeChatAttachmentPaths(paths: string[]): string[] {
  const normalized: string[] = [];
  const seen = new Set<string>();
  for (const rawPath of paths) {
    const path = String(rawPath ?? "").trim();
    if (!path || seen.has(path)) {
      continue;
    }
    seen.add(path);
    normalized.push(path);
  }
  return normalized;
}

/** Returns whether the desktop chat composer currently has sendable user input. */
export function canSubmitChatMessage(content: string, attachments: string[]): boolean {
  return content.trim().length > 0 || normalizeChatAttachmentPaths(attachments).length > 0;
}

/** Builds the one-line preview shown inside the desktop reply bar. */
export function summarizeChatReplyContent(content: string): string {
  const compactContent = content.replace(/\s+/g, " ").trim();
  if (!compactContent) {
    return "空消息";
  }
  return compactContent.length > 96 ? `${compactContent.slice(0, 96)}...` : compactContent;
}

/** Builds the optimistic user message shown before the desktop bridge confirms the send. */
export function buildOptimisticUserChatMessage(
  content: string,
  attachments: string[],
  replyTarget?: ChatReplyTarget | null,
): SessionMessage {
  const normalizedContent = content.trim();
  const media = normalizeChatAttachmentPaths(attachments);
  const message: SessionMessage = {
    role: "user",
    content: normalizedContent,
  };
  if (replyTarget) {
    message.metadata = {
      reply_to_message_id: replyTarget.messageId,
      reply_to_content: replyTarget.content,
      reply_to_sender: replyTarget.sender,
    };
  }
  if (media.length === 0) {
    return ensureChatMessageRenderId(message);
  }
  message.media = media;
  return ensureChatMessageRenderId(message);
}
