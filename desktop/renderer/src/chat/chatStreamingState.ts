import type { SessionPayload } from "../shared/types";
import { ensureChatMessageRenderId } from "./chatMessageIdentity";

/** Applies one bridge delta to the current transient assistant message. */
export function applyChatStreamDelta(
  session: SessionPayload,
  contentDelta: string,
  thinkingDelta: string,
): SessionPayload {
  if (!contentDelta && !thinkingDelta) return session;
  const messages = [...session.messages];
  const last = messages[messages.length - 1];
  if (last?.role === "assistant" && !last.id) {
    messages[messages.length - 1] = {
      ...last,
      content: last.content + contentDelta,
      reasoning_content: `${last.reasoning_content ?? ""}${thinkingDelta}`,
      streaming: true,
    };
  } else {
    messages.push(ensureChatMessageRenderId({
      role: "assistant",
      content: contentDelta,
      reasoning_content: thinkingDelta,
      streaming: true,
    }));
  }
  return { ...session, messages };
}

/** Marks the transient assistant message complete after the bridge emits chat.done. */
export function finishChatStream(session: SessionPayload): SessionPayload {
  const lastIndex = session.messages.length - 1;
  const last = session.messages[lastIndex];
  if (!last || last.role !== "assistant" || !last.streaming) return session;
  const messages = [...session.messages];
  messages[lastIndex] = {
    ...last,
    streaming: false,
    metadata: { ...last.metadata, streamed_reply: true },
  };
  return { ...session, messages };
}
