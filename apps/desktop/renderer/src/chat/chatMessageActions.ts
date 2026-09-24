import { isChatImageAsset } from "./chatImageHistory";
import { summarizeChatReplyContent } from "./chatComposerState";
import { normalizeSessionMediaPaths } from "./chatMedia";
import { roleChannelLabel, type RoleChannelCatalog } from "../roles/roleChannelCatalog";
import type { ChatReplyTarget, SessionMessage, SessionPayload } from "../shared/types";

export type MessageContextMenuState = {
  x: number;
  y: number;
  message: SessionMessage;
  messageKey: string;
  sender: string;
};

/** Which per-message actions (hover bar and context menu) one message offers right now. */
export type ChatMessageActionAvailability = {
  copy: boolean;
  quote: boolean;
  retry: boolean;
};

/** Returns the display name for an attachment path. */
export function getChatAttachmentName(path: string): string {
  return path.split(/[\\/]/).pop() || path;
}

/**
 * Resolves the channel label shown beneath one chat message (「桌面端」,
 * 「QQ」…), through the same `channels.list` catalog the role delivery panels
 * use; an unknown channel falls back to its raw name.
 */
export function getChatMessageSourceLabel(
  message: SessionPayload["messages"][number],
  catalog: RoleChannelCatalog = null,
): string | null {
  const metadata = message.metadata ?? {};
  const transportChannel = String(
    metadata.transport_channel ?? metadata.context_channel ?? metadata.source_channel ?? "",
  ).trim();
  if (transportChannel) return roleChannelLabel(transportChannel.toLowerCase(), catalog);
  return String(metadata.source ?? "").trim() === "desktop" ? roleChannelLabel("desktop", catalog) : null;
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

/** Whether this reply was stopped by the user mid-stream (persisted by the bridge as `interrupted_reply`). */
export function isInterruptedChatMessage(message: SessionMessage): boolean {
  return message.role === "assistant" && !message.streaming && message.metadata?.interrupted_reply === true;
}

/**
 * Decides which actions one message offers. A streaming reply offers none
 * (its text is still moving); quoting waits while a reply is in flight
 * because the composer is locked; retry is only for the failed turn the
 * caller marked as retryable (the latest error row with a user message to resend).
 */
export function getChatMessageActionAvailability(
  message: SessionMessage,
  { sending, retryable }: { sending: boolean; retryable: boolean },
): ChatMessageActionAvailability {
  if (message.streaming) return { copy: false, quote: false, retry: false };
  const isError = message.role === "error";
  return {
    copy: Boolean(getChatMessageCopyText(message)),
    quote: !isError && !sending && Boolean(getChatMessageReplyContent(message)),
    retry: isError && retryable && !sending,
  };
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
