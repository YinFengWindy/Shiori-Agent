import React from "react";
import { ChatMarkdownContent } from "./ChatMarkdownContent";
import { ChatReplyMetrics } from "./ChatReplyMetrics";
import { ChatThinkingBlock } from "./ChatThinkingBlock";
import { ChatToolCalls } from "./ChatToolCalls";
import { getStoredChatReplyPreview, isInterruptedChatMessage } from "./chatMessageActions";
import { getChatMessagePresentation } from "./chatMessagePresentation";
import { parseChatTurnMetrics } from "./chatTurnMetrics";
import { cx, type SessionMessage } from "@shiori/plugin-sdk";
import {
  focusResetClass, replyQuoteButtonClass, replyQuoteFrameClass, replyQuoteSenderClass, replyQuoteTextClass,
} from "../shared/styles";
import type { ChatReplyTarget } from "../shared/types";

function StoredReplyQuote({ preview }: { preview: ChatReplyTarget }) {
  return (
    <div className={cx(replyQuoteFrameClass, "text-left")}>
      {preview.sender ? (
        <div className={replyQuoteSenderClass}>{preview.sender}</div>
      ) : null}
      <div className={cx(replyQuoteTextClass, "line-clamp-2 text-ink-faint")}>{preview.preview}</div>
    </div>
  );
}

/** Whether a message has anything to draw inside its bubble (media-only messages do not). */
export function hasChatMessageBubbleContent(message: SessionMessage): boolean {
  const presentation = getChatMessagePresentation(message);
  return Boolean(
    message.content
    || getStoredChatReplyPreview(message)
    || message.streaming
    || presentation.finalThinking
    || presentation.toolChain.some((group) => group.calls.length > 0)
    || presentation.hasIntermediateNarrative
    || isInterruptedChatMessage(message),
  );
}

type ChatMessageBubbleBodyProps = {
  message: SessionMessage;
  onJumpToMessage: (messageKey: string) => void;
};

/** Everything inside one chat bubble: quote, thinking, tool calls, text and the finished-reply footer. */
export function ChatMessageBubbleBody({ message, onJumpToMessage }: ChatMessageBubbleBodyProps) {
  const isAssistant = message.role === "assistant";
  const isStreaming = Boolean(message.streaming);
  const storedReplyPreview = getStoredChatReplyPreview(message);
  const presentation = getChatMessagePresentation(message);
  const thinking = presentation.finalThinking;
  const turnMetrics = parseChatTurnMetrics(message.metadata?.turn_metrics);
  const thinkingDurationMs = turnMetrics.thinking_duration_ms;
  const toolChain = presentation.toolChain;
  const hasToolCalls = toolChain.some((group) => group.calls.length > 0);
  const showCursor = isStreaming && (message.content || !thinking);

  return (
    <>
      {storedReplyPreview ? (
        storedReplyPreview.messageId ? (
          <button
            className={cx(replyQuoteButtonClass, focusResetClass, "mb-2 block max-w-[420px]")}
            type="button"
            aria-label="跳转到被引用消息"
            onClick={() => onJumpToMessage(storedReplyPreview.messageId)}
          >
            <StoredReplyQuote preview={storedReplyPreview} />
          </button>
        ) : (
          <div className="mb-2 max-w-[420px]"><StoredReplyQuote preview={storedReplyPreview} /></div>
        )
      ) : null}
      {presentation.hasIntermediateNarrative ? (
        toolChain.map((group, groupIndex) => (
          <React.Fragment key={`tool-group:${groupIndex}`}>
            {group.reasoning_content.trim() ? (
              <ChatThinkingBlock content={group.reasoning_content} streaming={false} />
            ) : null}
            {group.text.trim() ? <ChatMarkdownContent content={group.text} /> : null}
            {group.calls.length ? <ChatToolCalls groups={[group]} streaming={isStreaming} /> : null}
          </React.Fragment>
        ))
      ) : (
        <>
          {thinking ? <ChatThinkingBlock content={thinking} streaming={isStreaming && !message.content} thinkingDurationMs={thinkingDurationMs} /> : null}
          {hasToolCalls ? <ChatToolCalls groups={toolChain} streaming={isStreaming} /> : null}
        </>
      )}
      {presentation.hasIntermediateNarrative && thinking ? (
        <ChatThinkingBlock
          content={thinking}
          streaming={isStreaming && !message.content}
          thinkingDurationMs={thinkingDurationMs}
        />
      ) : null}
      {!isAssistant ? (
        <div className="message-content whitespace-pre-wrap break-words">
          {message.content}
          {showCursor ? <span className="chat-stream-cursor ml-0.5" aria-hidden="true" /> : null}
        </div>
      ) : (
        <>
          <ChatMarkdownContent content={message.content} />
          {showCursor ? <span className="chat-stream-cursor ml-0.5" aria-hidden="true" /> : null}
        </>
      )}
      {!isStreaming ? (
        <ChatReplyMetrics
          metrics={turnMetrics}
          hasThinking={Boolean(thinking)}
          interrupted={isInterruptedChatMessage(message)}
        />
      ) : null}
    </>
  );
}
