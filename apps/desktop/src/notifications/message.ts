import type { BridgeEvent } from "@yinfengwindy/shiori-sdk/contract";
import { extractChatPreviewText } from "../shared/chatPreviewText.js";

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown> : null;
}

function text(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function boundedPreview(content: string) {
  const characters = Array.from(content);
  return characters.length > 160 ? `${characters.slice(0, 159).join("")}…` : content;
}

/** Selects only newly appended, committed desktop assistant messages, never history or streams. */
export function notificationMessages(event: BridgeEvent) {
  if (event.method !== "session.updated" || event.payload.change !== "message_appended") return [];
  const session = record(event.payload.session);
  const sessionKey = text(session?.key);
  const roleId = roleIdFromSessionKey(sessionKey);
  if (!roleId) return [];
  const metadata = record(session?.metadata);
  const title = text(metadata?.role_name) || roleId;
  // Only the explicit changed-message fields are authoritative; session.messages is history.
  const messages: unknown[] = Array.isArray(event.payload.messages)
    ? [...event.payload.messages, event.payload.message] : [event.payload.message];
  return messages.flatMap((value) => {
    const message = record(value);
    if (!message || message.role !== "assistant" || message.streaming) return [];
    const messageMetadata = record(message.metadata);
    const source = record(messageMetadata?.message_source);
    const channel = text(source?.channel) || text(messageMetadata?.transport_channel);
    if (channel && channel !== "desktop") return [];
    const id = text(message.id);
    const seq = Number.isSafeInteger(message.seq) && Number(message.seq) > 0 ? message.seq : null;
    // Every persisted message has an id/sequence; uncommitted placeholders must not alert.
    if (!id && !seq) return [];
    const hasMedia = Array.isArray(message.media) && message.media.some((path) => Boolean(text(path)));
    const body = extractChatPreviewText(text(message.content)) || (hasMedia ? "[图片]" : "");
    if (!body) return [];
    return [{ roleId, title, body: boundedPreview(body), key: `${sessionKey}:${id || `seq:${seq}`}` }];
  });
}
import { roleIdFromSessionKey } from "../bridge/sessionIdentity.js";
