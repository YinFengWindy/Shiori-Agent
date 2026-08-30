import type { SessionMessage, SessionPayload } from "../shared/types.js";
import { normalizeSessionMediaPaths } from "./chatMedia.js";

function normalizeMessageId(message: SessionMessage): string {
  return String(message.id ?? "").trim();
}

function normalizeClientMessageId(message: SessionMessage): string {
  return String(message.metadata?.client_message_id ?? "").trim();
}

function isInterruptedAssistantMessage(message: SessionMessage): boolean {
  return message.role === "assistant" && message.metadata?.interrupted_reply === true;
}

function normalizeReplyMetadata(message: SessionMessage) {
  return {
    messageId: String(message.metadata?.reply_to_message_id ?? "").trim(),
    content: String(message.metadata?.reply_to_content ?? "").trim(),
    sender: String(message.metadata?.reply_to_sender ?? "").trim(),
  };
}

function normalizeMedia(message: SessionMessage): string[] {
  return normalizeSessionMediaPaths(message.media);
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
  optimisticUserMessage: SessionMessage | null,
  incomingSession: SessionPayload,
): SessionMessage | null {
  if (!optimisticUserMessage || !isOptimisticUserMessage(optimisticUserMessage)) {
    return null;
  }
  const clientMessageId = normalizeClientMessageId(optimisticUserMessage);
  const alreadyPersisted = incomingSession.messages.some((message) => {
    if (clientMessageId) {
      return normalizeClientMessageId(message) === clientMessageId;
    }
    return areEquivalentMessagesIgnoringMissingIds(optimisticUserMessage, message);
  });
  return alreadyPersisted ? null : optimisticUserMessage;
}

function findIncomingMessageIndex(
  message: SessionMessage,
  incomingSession: SessionPayload,
): number {
  const clientMessageId = normalizeClientMessageId(message);
  if (clientMessageId) {
    return incomingSession.messages.findIndex((incomingMessage) => (
      normalizeClientMessageId(incomingMessage) === clientMessageId
    ));
  }
  return incomingSession.messages.findIndex((incomingMessage) => (
    Boolean(normalizeMessageId(incomingMessage))
      && areEquivalentMessagesIgnoringMissingIds(message, incomingMessage)
  ));
}

function findAcknowledgedUserMessageIndex(
  pendingUserMessage: SessionMessage,
  incomingSession: SessionPayload,
): number {
  return findIncomingMessageIndex(pendingUserMessage, incomingSession);
}

function findNextIncomingMessageIndex(
  currentMessages: SessionMessage[],
  startIndex: number,
  incomingSession: SessionPayload,
): number {
  for (let index = startIndex + 1; index < currentMessages.length; index += 1) {
    const incomingIndex = findIncomingMessageIndex(currentMessages[index], incomingSession);
    if (incomingIndex >= 0) return incomingIndex;
  }
  return -1;
}

function findCurrentPendingUserIndex(
  currentSession: SessionPayload,
  pendingUserMessage: SessionMessage,
): number {
  const clientMessageId = normalizeClientMessageId(pendingUserMessage);
  if (clientMessageId) {
    return currentSession.messages.findIndex((message) => (
      normalizeClientMessageId(message) === clientMessageId
    ));
  }
  return currentSession.messages.findIndex((message) => (
    areEquivalentMessagesIgnoringMissingIds(pendingUserMessage, message)
  ));
}

function preserveInterruptedAssistantTrace(
  currentSession: SessionPayload,
  incomingSession: SessionPayload,
  pendingUserMessage: SessionMessage | null,
): SessionPayload {
  if (!pendingUserMessage || !isPendingUserMessageAcknowledged(pendingUserMessage, incomingSession)) {
    return incomingSession;
  }
  const incomingUserIndex = findAcknowledgedUserMessageIndex(pendingUserMessage, incomingSession);
  if (incomingUserIndex < 0) return incomingSession;
  const currentUserIndex = findCurrentPendingUserIndex(currentSession, pendingUserMessage);
  const interruptedMessagesByIncomingIndex = new Map<number, SessionMessage[]>();
  currentSession.messages.forEach((message, index) => {
    if (!isInterruptedAssistantMessage(message) || (currentUserIndex >= 0 && index >= currentUserIndex)) {
      return;
    }
    if (findIncomingMessageIndex(message, incomingSession) >= 0) return;
    const anchorIndex = findNextIncomingMessageIndex(currentSession.messages, index, incomingSession);
    const targetIndex = anchorIndex >= 0 ? anchorIndex : incomingUserIndex;
    const anchoredMessages = interruptedMessagesByIncomingIndex.get(targetIndex) ?? [];
    anchoredMessages.push(message);
    interruptedMessagesByIncomingIndex.set(targetIndex, anchoredMessages);
  });
  const interruptedMessages = [...interruptedMessagesByIncomingIndex.values()].flat();
  if (interruptedMessages.length === 0) return incomingSession;
  return {
    ...incomingSession,
    metadata: {
      ...(currentSession.metadata ?? {}),
      ...(incomingSession.metadata ?? {}),
    },
    messages: incomingSession.messages.flatMap((message, index) => [
      ...(interruptedMessagesByIncomingIndex.get(index) ?? []),
      message,
    ]),
  };
}

/** Returns whether an authoritative session contains the persisted form of one pending user message. */
export function isPendingUserMessageAcknowledged(
  pendingUserMessage: SessionMessage,
  incomingSession: SessionPayload,
): boolean {
  const clientMessageId = normalizeClientMessageId(pendingUserMessage);
  return incomingSession.messages.some((message) => {
    const incomingClientMessageId = normalizeClientMessageId(message);
    if (clientMessageId) {
      return clientMessageId === incomingClientMessageId;
    }
    return Boolean(normalizeMessageId(message))
      && areEquivalentMessagesIgnoringMissingIds(pendingUserMessage, message);
  });
}

/** Clears a pending user overlay only after its chat turn has finished and a snapshot confirms it. */
export function shouldClearPendingUserMessage(
  pendingUserMessage: SessionMessage,
  incomingSession: SessionPayload,
  sending: boolean,
): boolean {
  return !sending && isPendingUserMessageAcknowledged(pendingUserMessage, incomingSession);
}

function hasEquivalentIncomingPrefix(
  currentSession: SessionPayload,
  incomingSession: SessionPayload,
): boolean {
  if (incomingSession.messages.length >= currentSession.messages.length) {
    return false;
  }
  return incomingSession.messages.every((incomingMessage, index) => (
    areEquivalentMessagesIgnoringMissingIds(currentSession.messages[index], incomingMessage)
  ));
}

function preserveCurrentMessageTail(
  currentSession: SessionPayload,
  incomingSession: SessionPayload,
): SessionPayload {
  return {
    ...incomingSession,
    metadata: {
      ...(currentSession.metadata ?? {}),
      ...(incomingSession.metadata ?? {}),
    },
    messages: [
      ...incomingSession.messages,
      ...currentSession.messages.slice(incomingSession.messages.length),
    ],
  };
}

/** Keeps the local optimistic user turn visible while older session snapshots are still arriving. */
export function mergeIncomingSessionDuringSend(
  currentSession: SessionPayload | null,
  incomingSession: SessionPayload | null,
  sending: boolean,
  pendingUserMessage: SessionMessage | null = null,
): SessionPayload | null {
  if (!incomingSession) {
    return incomingSession;
  }

  if (!currentSession || currentSession.key !== incomingSession.key) {
    if (!pendingUserMessage || isPendingUserMessageAcknowledged(pendingUserMessage, incomingSession)) {
      return incomingSession;
    }
    return {
      ...incomingSession,
      messages: [...incomingSession.messages, pendingUserMessage],
    };
  }

  const pendingClientMessageId = pendingUserMessage
    ? normalizeClientMessageId(pendingUserMessage)
    : "";
  const pendingUserIndex = pendingClientMessageId
    ? currentSession.messages.findIndex((message) => (
        normalizeClientMessageId(message) === pendingClientMessageId
      ))
    : -1;

  if (
    (!pendingUserMessage || pendingUserIndex >= 0)
    && hasEquivalentIncomingPrefix(currentSession, incomingSession)
  ) {
    return preserveCurrentMessageTail(currentSession, incomingSession);
  }

  const currentOptimisticUserIndex = findOptimisticUserIndex(currentSession.messages);
  const optimisticUserIndex = pendingUserMessage
    ? (pendingUserIndex >= 0 ? pendingUserIndex : currentSession.messages.length)
    : currentOptimisticUserIndex;
  const optimisticUserMessage = pendingUserMessage
    ?? currentSession.messages[currentOptimisticUserIndex]
    ?? null;
  const missingOptimisticUserMessage = findMissingOptimisticUserMessage(
    optimisticUserMessage,
    incomingSession,
  );

  const incomingWithInterruptedTrace = preserveInterruptedAssistantTrace(
    currentSession,
    incomingSession,
    pendingUserMessage,
  );
  if (incomingWithInterruptedTrace !== incomingSession) {
    return incomingWithInterruptedTrace;
  }

  if (!sending && !missingOptimisticUserMessage) {
    return incomingSession;
  }

  if (!missingOptimisticUserMessage) {
    return incomingSession;
  }

  if (
    !normalizeClientMessageId(missingOptimisticUserMessage)
    && !hasMatchingPersistedPrefixBeforeOptimisticUser(currentSession, incomingSession, optimisticUserIndex)
  ) {
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
