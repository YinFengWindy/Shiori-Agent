import type { SessionMessage, SessionPayload } from "../shared/types";

function normalizeMessageId(message: SessionMessage): string {
  return String(message.id ?? "").trim();
}

function normalizeReplyMetadata(message: SessionMessage) {
  return {
    messageId: String(message.metadata?.reply_to_message_id ?? "").trim(),
    content: String(message.metadata?.reply_to_content ?? "").trim(),
    sender: String(message.metadata?.reply_to_sender ?? "").trim(),
  };
}

function normalizeMedia(message: SessionMessage): string[] {
  return (message.media ?? []).map((item) => item.trim());
}

function sameMedia(left: SessionMessage, right: SessionMessage): boolean {
  const leftMedia = normalizeMedia(left);
  const rightMedia = normalizeMedia(right);
  if (leftMedia.length !== rightMedia.length) {
    return false;
  }
  return leftMedia.every((item, index) => item === rightMedia[index]);
}

function areEquivalentMessages(left: SessionMessage, right: SessionMessage): boolean {
  const leftId = normalizeMessageId(left);
  const rightId = normalizeMessageId(right);
  if (leftId || rightId) {
    if (!leftId || !rightId || leftId !== rightId) {
      return false;
    }
  }
  if (left.role !== right.role || left.content !== right.content || !sameMedia(left, right)) {
    return false;
  }
  const leftReply = normalizeReplyMetadata(left);
  const rightReply = normalizeReplyMetadata(right);
  return leftReply.messageId === rightReply.messageId
    && leftReply.content === rightReply.content
    && leftReply.sender === rightReply.sender;
}

function isIncomingPrefixOfCurrent(currentSession: SessionPayload, incomingSession: SessionPayload): boolean {
  if (incomingSession.messages.length >= currentSession.messages.length) {
    return false;
  }
  return incomingSession.messages.every((message, index) => areEquivalentMessages(message, currentSession.messages[index]));
}

/** Keeps locally rendered optimistic chat messages visible while an older session snapshot is still arriving. */
export function mergeIncomingSessionDuringSend(
  currentSession: SessionPayload | null,
  incomingSession: SessionPayload | null,
  sending: boolean,
): SessionPayload | null {
  if (!currentSession || !incomingSession || !sending || currentSession.key !== incomingSession.key) {
    return incomingSession;
  }
  if (!isIncomingPrefixOfCurrent(currentSession, incomingSession)) {
    return incomingSession;
  }
  return {
    ...incomingSession,
    messages: currentSession.messages,
  };
}
