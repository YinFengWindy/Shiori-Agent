import { isChatImageAsset } from "./chatImageHistory";
import { summarizeChatReplyContent } from "./chatComposerState";
import { normalizeSessionMediaPaths } from "./chatMedia";
import type { ChatReplyTarget, SessionMessage, SessionPayload } from "../shared/types";

export type MessageContextMenuState = {
  x: number;
  y: number;
  message: SessionMessage;
  messageKey: string;
  sender: string;
};

/** Returns the display name for an attachment path. */
export function getChatAttachmentName(path: string): string {
  return path.split(/[\\/]/).pop() || path;
}

/** Resolves the transport label shown beneath one chat message. */
export function getChatMessageSourceLabel(
  message: SessionPayload["messages"][number],
): string | null {
  const metadata = message.metadata ?? {};
  const transportChannel = String(
    metadata.transport_channel ?? metadata.context_channel ?? metadata.source_channel ?? "",
  ).trim();
  if (transportChannel) return transportChannel.toUpperCase();
  return String(metadata.source ?? "").trim() === "desktop" ? "DESKTOP" : null;
}

/** Returns copyable text for a chat message. */
export function getChatMessageCopyText(message: SessionMessage): string {
  return message.content.trim();
}

/** Returns the text or media placeholder used when quoting a chat message. */
export function getChatMessageReplyContent(message: SessionMessage): string {
  const content = message.content.trim();
  if (content) return content;
  const media = normalizeSessionMediaPaths(message.media);
  if (!media.length) return "";
  return media.some((item) => isChatImageAsset(item)) ? "[图片]" : "[附件]";
}

/** Reads the persisted reply preview attached to one chat message. */
export function getStoredChatReplyPreview(message: SessionMessage): ChatReplyTarget | null {
  const metadata = message.metadata ?? {};
  const replyContent = String(metadata.reply_to_content ?? "").trim();
  if (!replyContent) return null;
  return {
    messageId: String(metadata.reply_to_message_id ?? "").trim(),
    content: replyContent,
    sender: String(metadata.reply_to_sender ?? "").trim(),
    preview: summarizeChatReplyContent(replyContent),
  };
}
