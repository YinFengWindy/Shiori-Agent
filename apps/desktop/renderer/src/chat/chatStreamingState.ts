import type { ChatToolCall, ChatTurnMetrics, SessionMessage, SessionPayload } from "../shared/types";
import { ensureChatMessageRenderId } from "./chatMessageIdentity";

/** Applies one bridge delta to the current transient assistant message. */
export function applyChatStreamDelta(
  session: SessionPayload,
  contentDelta: string,
  thinkingDelta: string,
  turnId = "",
): SessionPayload {
  if (!contentDelta && !thinkingDelta) return session;
  return updateTransientAssistant(session, turnId, (message) => ({
    ...message,
    content: message.content + contentDelta,
    reasoning_content: `${message.reasoning_content ?? ""}${thinkingDelta}`,
  }));
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
  messages[lastIndex] = finishAssistantMessage(last, metrics);
  return { ...session, messages };
}

/** Ends failed-turn traces, including rows followed by a persisted proactive reply. */
export function failChatStream(session: SessionPayload): SessionPayload {
  let changed = false;
  const messages = session.messages.map((message) => {
    if (message.role !== "assistant" || !message.streaming) return message;
    changed = true;
    return {
      ...finishAssistantMessage(message),
      ...(message.tool_chain ? {
        tool_chain: message.tool_chain.map((group) => ({
          ...group,
          calls: group.calls.map((call) => call.status === "running"
            ? { ...call, status: "error" }
            : call),
        })),
      } : {}),
    };
  });
  return changed ? { ...session, messages } : session;
}

function finishAssistantMessage(message: SessionMessage, metrics: ChatTurnMetrics = {}) {
  return {
    ...message,
    streaming: false,
    metadata: {
      ...message.metadata,
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
  turnId?: string;
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
  return updateTransientAssistantTool(session, event, {
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
  return updateTransientAssistantTool(session, event, {
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
  event: ToolStartedEvent,
  toolCall: ChatToolCall,
): SessionPayload {
  return updateTransientAssistant(session, event.turnId ?? "", (message) => (
    mergeToolCall(message, event.iteration, toolCall)
  ));
}

function updateTransientAssistant(
  session: SessionPayload,
  turnId: string,
  update: (message: SessionMessage) => SessionMessage,
): SessionPayload {
  const messages = [...session.messages];
  const last = messages[messages.length - 1];
  const normalizedTurnId = turnId.trim();
  // Text, thinking, and tool-first traces share an identity, but another turn's
  // unfinished trace must never receive this turn's deltas.
  const assistant = last?.role === "assistant" && !last.id && last.seq == null && last.streaming === true
    && String(last.metadata?.turn_id ?? "").trim() === normalizedTurnId
    ? last
    : ensureChatMessageRenderId({
        role: "assistant", content: "", streaming: true,
        ...(normalizedTurnId ? { metadata: { turn_id: normalizedTurnId } } : {}),
      });
  const nextAssistant = update(assistant);
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
