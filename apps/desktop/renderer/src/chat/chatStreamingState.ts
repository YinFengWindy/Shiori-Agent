import type { ChatToolCall, SessionMessage, SessionPayload } from "@yinfengwindy/shiori-sdk";
import type { ChatTurnMetrics } from "../shared/types";
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
  }), { createIfMissing: true });
}

/** Completes a transient reply; terminal callers must supply the event's owning turn identity. */
export function finishChatStream(
  session: SessionPayload,
  metrics: ChatTurnMetrics = {},
  turnId: string,
): SessionPayload {
  return updateTransientAssistant(session, turnId, (message) => finishAssistantMessage(message, metrics));
}

/** Ends the required turn's failed trace and running tools without changing other replies. */
export function failChatStream(session: SessionPayload, turnId: string): SessionPayload {
  return updateTransientAssistant(session, turnId, (message) => ({
    ...finishAssistantMessage(message),
    ...(message.tool_chain ? {
      tool_chain: message.tool_chain.map((group) => ({
        ...group,
        calls: group.calls.map((call) => call.status === "running"
          ? { ...call, status: "error" }
          : call),
      })),
    } : {}),
  }));
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

/** Marks the required turn's transient reply interrupted while retaining its local trace. */
export function interruptChatStream(session: SessionPayload, turnId: string): SessionPayload {
  return updateTransientAssistant(session, turnId, (message) => ({
    ...message,
    streaming: false,
    metadata: {
      ...message.metadata,
      streamed_reply: true,
      interrupted_reply: true,
    },
  }));
}

/** Finishes cancellation using the backend's final state and the required owning turn identity. */
export function finalizeChatCancellation(
  session: SessionPayload,
  status: "interrupted" | "idle",
  turnId: string,
): SessionPayload {
  return status === "interrupted" ? interruptChatStream(session, turnId) : finishChatStream(session, {}, turnId);
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
  ), { createIfMissing: true });
}

function findTransientAssistantIndex(messages: readonly SessionMessage[], turnId: string) {
  const normalizedTurnId = turnId.trim();
  // Independent deliveries can follow a streaming reply. Its turn identity,
  // rather than its position, owns subsequent deltas and terminal events.
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index]!;
    if (message.role === "assistant" && !message.id && message.seq == null && message.streaming === true
      && String(message.metadata?.turn_id ?? "").trim() === normalizedTurnId) return index;
  }
  return -1;
}

function updateTransientAssistant(
  session: SessionPayload,
  turnId: string,
  update: (message: SessionMessage) => SessionMessage,
  { createIfMissing = false } = {},
): SessionPayload {
  const index = findTransientAssistantIndex(session.messages, turnId);
  // Persistence may acknowledge the reply before its terminal event. Completing
  // that turn must leave the authoritative message and metrics untouched.
  if (index < 0 && !createIfMissing) return session;
  const messages = [...session.messages];
  const normalizedTurnId = turnId.trim();
  const assistant = index >= 0
    ? messages[index]!
    : ensureChatMessageRenderId({
        role: "assistant", content: "", streaming: true,
        ...(normalizedTurnId ? { metadata: { turn_id: normalizedTurnId } } : {}),
      });
  const nextAssistant = update(assistant);
  if (index >= 0) {
    messages[index] = nextAssistant;
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
