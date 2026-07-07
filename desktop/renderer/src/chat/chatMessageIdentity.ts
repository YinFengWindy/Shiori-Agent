import type { SessionMessage, SessionPayload } from "../shared/types";
import { normalizeSessionMediaPaths } from "./chatMedia";

const localChatMessageRenderIdPrefix = "local";
let nextLocalChatMessageRenderId = 0;

function normalizeMessageId(message: SessionMessage): string {
  return String(message.id ?? "").trim();
}

function normalizeRenderId(message: SessionMessage): string {
  return String(message.render_id ?? "").trim();
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

function sameReplyMetadata(left: SessionMessage, right: SessionMessage): boolean {
  const leftReply = normalizeReplyMetadata(left);
  const rightReply = normalizeReplyMetadata(right);
  return leftReply.messageId === rightReply.messageId
    && leftReply.content === rightReply.content
    && leftReply.sender === rightReply.sender;
}

function canReuseRenderIdForStreamingUpdate(current: SessionMessage, incoming: SessionMessage): boolean {
  const currentId = normalizeMessageId(current);
  const incomingId = normalizeMessageId(incoming);
  if (currentId && incomingId && currentId !== incomingId) {
    return false;
  }
  if (current.role !== incoming.role || !sameMedia(current, incoming) || !sameReplyMetadata(current, incoming)) {
    return false;
  }
  const currentContent = current.content;
  const incomingContent = incoming.content;
  if (currentContent === incomingContent) {
    return true;
  }
  const shorterContent = currentContent.length <= incomingContent.length ? currentContent : incomingContent;
  const longerContent = currentContent.length > incomingContent.length ? currentContent : incomingContent;
  return Boolean(shorterContent) && longerContent.startsWith(shorterContent);
}

function createLocalChatMessageRenderId(role: string): string {
  nextLocalChatMessageRenderId += 1;
  return `${localChatMessageRenderIdPrefix}:${role}:${nextLocalChatMessageRenderId}`;
}

function createServerChatMessageRenderId(messageId: string): string {
  return `server:${messageId}`;
}

/** Returns the stable React key for one rendered chat message. */
export function getChatMessageReactKey(message: SessionMessage, index: number): string {
  return normalizeRenderId(message)
    || normalizeMessageId(message)
    || `${message.role}-${index}`;
}

/** Returns the DOM lookup key for one rendered chat message. */
export function getChatMessageDomKey(message: SessionMessage, index: number): string {
  return normalizeMessageId(message) || `${message.role}-${index}`;
}

/** Ensures one chat message carries a stable render identity before it is shown in the desktop UI. */
export function ensureChatMessageRenderId(message: SessionMessage): SessionMessage {
  const renderId = normalizeRenderId(message);
  if (renderId) {
    return message;
  }
  const messageId = normalizeMessageId(message);
  return {
    ...message,
    render_id: messageId ? createServerChatMessageRenderId(messageId) : createLocalChatMessageRenderId(message.role),
  };
}

/** Reuses local render identities when an authoritative session snapshot replaces optimistic or streaming messages. */
export function reconcileSessionMessageRenderIds(
  currentSession: SessionPayload | null,
  incomingSession: SessionPayload | null,
): SessionPayload | null {
  if (!incomingSession) {
    return null;
  }

  const currentMessages = currentSession?.messages ?? [];
  let nextCurrentSearchStart = 0;
  let changed = false;

  const nextMessages = incomingSession.messages.map((incomingMessage) => {
    let matchedCurrentMessage: SessionMessage | null = null;
    for (let currentIndex = nextCurrentSearchStart; currentIndex < currentMessages.length; currentIndex += 1) {
      const currentMessage = currentMessages[currentIndex];
      if (!canReuseRenderIdForStreamingUpdate(currentMessage, incomingMessage)) {
        continue;
      }
      matchedCurrentMessage = currentMessage;
      nextCurrentSearchStart = currentIndex + 1;
      break;
    }

    if (matchedCurrentMessage) {
      const matchedRenderId = normalizeRenderId(matchedCurrentMessage);
      if (matchedRenderId && matchedRenderId !== normalizeRenderId(incomingMessage)) {
        changed = true;
        return {
          ...incomingMessage,
          render_id: matchedRenderId,
        };
      }
    }

    const ensuredMessage = ensureChatMessageRenderId(incomingMessage);
    if (ensuredMessage !== incomingMessage) {
      changed = true;
    }
    return ensuredMessage;
  });

  if (!changed) {
    return incomingSession;
  }
  return {
    ...incomingSession,
    messages: nextMessages,
  };
}
