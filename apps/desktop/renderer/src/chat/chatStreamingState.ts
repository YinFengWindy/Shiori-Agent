import type { ChatToolCall, ChatTurnMetrics, SessionMessage, SessionPayload } from "../shared/types";
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
export function finishChatStream(
  session: SessionPayload,
  metrics: ChatTurnMetrics = {},
): SessionPayload {
  const lastIndex = session.messages.length - 1;
  const last = session.messages[lastIndex];
  if (!last || last.role !== "assistant" || !last.streaming) return session;
  const messages = [...session.messages];
  messages[lastIndex] = {
    ...last,
    streaming: false,
    metadata: {
      ...last.metadata,
      streamed_reply: true,
      ...(metrics.total_tokens !== undefined || metrics.thinking_duration_ms !== undefined
        ? {
            turn_metrics: {
              ...(typeof metrics.total_tokens === "number" ? { total_tokens: metrics.total_tokens } : {}),
              ...(typeof metrics.thinking_duration_ms === "number" ? { thinking_duration_ms: metrics.thinking_duration_ms } : {}),
            },
          }
        : {}),
    },
  };
  return { ...session, messages };
}

/** Marks a cancelled transient assistant reply complete while retaining its local trace for the next turn. */
export function interruptChatStream(session: SessionPayload): SessionPayload {
  const lastIndex = session.messages.length - 1;
  const last = session.messages[lastIndex];
  if (!last || last.role !== "assistant" || !last.streaming) return session;
  const messages = [...session.messages];
  messages[lastIndex] = {
    ...last,
    streaming: false,
    metadata: {
      ...last.metadata,
      streamed_reply: true,
      interrupted_reply: true,
    },
  };
  return { ...session, messages };
}

/** Finishes cancellation according to the backend's final turn state. */
export function finalizeChatCancellation(
  session: SessionPayload,
  status: "interrupted" | "idle",
): SessionPayload {
  return status === "interrupted" ? interruptChatStream(session) : finishChatStream(session);
}

type ToolStartedEvent = {
  iteration: number;
  callId: string;
  toolName: string;
  arguments: Record<string, unknown>;
};

type ToolCompletedEvent = ToolStartedEvent & {
  finalArguments: Record<string, unknown>;
  status: string;
  resultPreview: string;
};

/** Adds one running tool call to the current transient assistant reply. */
export function applyChatToolStarted(
  session: SessionPayload,
  event: ToolStartedEvent,
): SessionPayload {
  if (!event.callId.trim() || !event.toolName.trim()) return session;
  return updateTransientAssistantTool(session, event.iteration, {
    call_id: event.callId,
    name: event.toolName,
    status: "running",
    arguments: event.arguments,
    final_arguments: {},
    result: "",
  });
}

/** Completes one transient tool call using its sanitized result preview. */
export function applyChatToolCompleted(
  session: SessionPayload,
  event: ToolCompletedEvent,
): SessionPayload {
  if (!event.callId.trim() || !event.toolName.trim()) return session;
  return updateTransientAssistantTool(session, event.iteration, {
    call_id: event.callId,
    name: event.toolName,
    status: event.status,
    arguments: event.arguments,
    final_arguments: event.finalArguments,
    result: event.resultPreview,
  });
}

function updateTransientAssistantTool(
  session: SessionPayload,
  iteration: number,
  toolCall: ChatToolCall,
): SessionPayload {
  const messages = [...session.messages];
  const last = messages[messages.length - 1];
  const assistant = last?.role === "assistant" && !last.id
    ? last
    : ensureChatMessageRenderId({ role: "assistant", content: "", streaming: true });
  const nextAssistant = mergeToolCall(assistant, iteration, toolCall);
  if (assistant === last) {
    messages[messages.length - 1] = nextAssistant;
  } else {
    messages.push(nextAssistant);
  }
  return { ...session, messages };
}

function mergeToolCall(
  message: SessionMessage,
  iteration: number,
  toolCall: ChatToolCall,
): SessionMessage {
  const groups = [...(message.tool_chain ?? [])];
  const groupIndex = Math.max(0, iteration - 1);
  while (groups.length <= groupIndex) {
    groups.push({ text: "", reasoning_content: "", calls: [] });
  }
  const group = groups[groupIndex]!;
  const calls = [...group.calls];
  const callIndex = calls.findIndex((call) => call.call_id === toolCall.call_id);
  if (callIndex >= 0) {
    calls[callIndex] = toolCall;
  } else {
    calls.push(toolCall);
  }
  groups[groupIndex] = { ...group, calls };
  return { ...message, streaming: true, tool_chain: groups };
}
