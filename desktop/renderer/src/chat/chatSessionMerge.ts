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

function areEquivalentMessagesIgnoringMissingIds(left: SessionMessage, right: SessionMessage): boolean {
  const leftId = normalizeMessageId(left);
  const rightId = normalizeMessageId(right);
  if (leftId && rightId && leftId !== rightId) {
    return false;
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

function isOptimisticUserMessage(message: SessionMessage): boolean {
  return message.role === "user" && !normalizeMessageId(message);
}

function findOptimisticUserIndex(messages: SessionMessage[]): number {
  return messages.findIndex(isOptimisticUserMessage);
}

function hasMatchingPersistedPrefixBeforeOptimisticUser(
  currentSession: SessionPayload,
  incomingSession: SessionPayload,
  optimisticUserIndex: number,
): boolean {
  if (optimisticUserIndex <= 0) {
    return true;
  }
  if (incomingSession.messages.length < optimisticUserIndex) {
    return false;
  }
  return currentSession.messages
    .slice(0, optimisticUserIndex)
    .every((message, index) => areEquivalentMessages(message, incomingSession.messages[index]));
}

function findMissingOptimisticUserMessage(
  currentSession: SessionPayload,
  incomingSession: SessionPayload,
  optimisticUserIndex: number,
): SessionMessage | null {
  if (optimisticUserIndex < 0) {
    return null;
  }
  const optimisticUserMessage = currentSession.messages[optimisticUserIndex];
  if (!optimisticUserMessage || !isOptimisticUserMessage(optimisticUserMessage)) {
    return null;
  }
  const alreadyPersisted = incomingSession.messages.some((message) => (
    areEquivalentMessagesIgnoringMissingIds(optimisticUserMessage, message)
  ));
  return alreadyPersisted ? null : optimisticUserMessage;
}

/** Keeps the local optimistic user turn visible while older session snapshots are still arriving. */
export function mergeIncomingSessionDuringSend(
  currentSession: SessionPayload | null,
  incomingSession: SessionPayload | null,
  sending: boolean,
): SessionPayload | null {
  if (!currentSession || !incomingSession || currentSession.key !== incomingSession.key) {
    return incomingSession;
  }

  const optimisticUserIndex = findOptimisticUserIndex(currentSession.messages);
  const missingOptimisticUserMessage = findMissingOptimisticUserMessage(
    currentSession,
    incomingSession,
    optimisticUserIndex,
  );

  if (!sending && !missingOptimisticUserMessage) {
    return incomingSession;
  }

  if (!missingOptimisticUserMessage) {
    return incomingSession;
  }

  if (!hasMatchingPersistedPrefixBeforeOptimisticUser(currentSession, incomingSession, optimisticUserIndex)) {
    return incomingSession;
  }

  return {
    ...incomingSession,
    metadata: {
      ...(currentSession.metadata ?? {}),
      ...(incomingSession.metadata ?? {}),
    },
    messages: [
      ...incomingSession.messages.slice(0, optimisticUserIndex),
      missingOptimisticUserMessage,
      ...incomingSession.messages.slice(optimisticUserIndex),
    ],
  };
}
