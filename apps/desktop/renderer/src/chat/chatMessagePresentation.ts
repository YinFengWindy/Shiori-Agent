import type { ChatToolCallGroup, SessionMessage } from "../shared/types";

export type ChatMessagePresentation = {
  finalThinking: string;
  toolChain: ChatToolCallGroup[];
  hasIntermediateNarrative: boolean;
};

/** Selects the persisted and transient assistant sections that belong in one chat bubble. */
export function getChatMessagePresentation(message: SessionMessage): ChatMessagePresentation {
  const isStreaming = Boolean(message.streaming);
  const wasStreamed = Boolean(message.metadata?.streamed_reply);
  const finalThinking = isStreaming || wasStreamed || !message.id
    ? String(message.reasoning_content ?? "")
    : "";
  const toolChain = message.tool_chain ?? [];
  return {
    finalThinking,
    toolChain,
    hasIntermediateNarrative: toolChain.some((group) => (
      Boolean(group.text.trim()) || Boolean(group.reasoning_content.trim())
    )),
  };
}
