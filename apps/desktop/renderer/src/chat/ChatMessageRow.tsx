import React, { useCallback } from "react";
import { ChatMessageAttachments } from "./ChatMessageAttachments";
import { ChatMarkdownContent } from "./ChatMarkdownContent";
import { ChatReplyMetrics } from "./ChatReplyMetrics";
import { ChatThinkingBlock } from "./ChatThinkingBlock";
import { ChatToolCalls } from "./ChatToolCalls";
import {
  getChatMessageSourceLabel,
  getStoredChatReplyPreview,
} from "./chatMessageActions";
import { getChatMessageDomKey } from "./chatMessageIdentity";
import { getChatMessagePresentation } from "./chatMessagePresentation";
import { parseChatTurnMetrics } from "./chatTurnMetrics";
import { formatTimestamp, toFileUrl } from "../shared/format";
import { cx } from "../shared/styles";
import type { RoleRecord, SessionMessage } from "../shared/types";

type ChatMessageRowProps = {
  activeRole: RoleRecord | null;
  index: number;
  isHighlighted: boolean;
  message: SessionMessage;
  onBeginAttachmentDrag: (path: string) => void;
  onJumpToMessage: (messageKey: string) => void;
  onMeasureElement?: (message: SessionMessage, index: number, element: HTMLElement | null) => void;
  onOpenContextMenu: (
    event: React.MouseEvent<HTMLElement>,
    message: SessionMessage,
    messageKey: string,
    sender: string,
  ) => void;
  onOpenImagePreview: (historyKey: string) => void;
};

const agentAvatarClass =
  "message-avatar grid h-8 w-8 flex-none place-items-center overflow-hidden rounded-full border border-black/10 bg-[#f6f6f6] object-cover";
const chatMinorTextClass = "text-[12px]";
const assistantMessageBubbleClass =
  "message-bubble w-fit max-w-full rounded-[14px] border border-[rgba(228,228,228,0.66)] bg-[rgba(255,255,255,0.78)] px-3.5 py-2.5 text-left shadow-[0_1px_2px_rgba(0,0,0,0.03)] transition-colors duration-150 group-hover:bg-[rgba(255,255,255,0.9)]";
const userMessageBubbleClass =
  "message-bubble w-fit max-w-full rounded-[14px] border border-[#E4E4E4] bg-white px-3.5 py-2.5 text-left shadow-[0_1px_2px_rgba(0,0,0,0.04)]";

/** Renders one independently memoized chat message so unaffected Markdown stays out of updates. */
export const ChatMessageRow = React.memo(function ChatMessageRow({
  activeRole,
  index,
  isHighlighted,
  message,
  onBeginAttachmentDrag,
  onJumpToMessage,
  onMeasureElement,
  onOpenContextMenu,
  onOpenImagePreview,
}: ChatMessageRowProps) {
  const isUser = message.role === "user";
  const isError = message.role === "error";
  const isAssistant = message.role === "assistant";
  const authorLabel = isError ? "系统提示" : (isUser ? "你" : (activeRole?.name || "Agent"));
  const messageDomKey = getChatMessageDomKey(message, index);
  const sourceLabel = getChatMessageSourceLabel(message);
  const storedReplyPreview = getStoredChatReplyPreview(message);
  const isStreaming = Boolean(message.streaming);
  const presentation = getChatMessagePresentation(message);
  const thinking = presentation.finalThinking;
  const turnMetrics = parseChatTurnMetrics(message.metadata?.turn_metrics);
  const thinkingDurationMs = turnMetrics.thinking_duration_ms;
  const toolChain = presentation.toolChain;
  const hasToolCalls = toolChain.some((group) => group.calls.length > 0);
  const bubbleClass = isError
    ? "message-bubble w-fit max-w-full rounded-[14px] border border-[rgba(176,58,58,0.22)] bg-[rgba(255,244,244,0.96)] px-3.5 py-2.5 text-left text-[#8f2d2d] shadow-[0_1px_2px_rgba(0,0,0,0.04)]"
    : isUser
      ? userMessageBubbleClass
      : assistantMessageBubbleClass;
  const measureElement = useCallback((element: HTMLElement | null) => {
    onMeasureElement?.(message, index, element);
  }, [index, message, onMeasureElement]);
  const openContextMenu = useCallback((event: React.MouseEvent<HTMLElement>) => {
    onOpenContextMenu(event, message, messageDomKey, authorLabel);
  }, [authorLabel, message, messageDomKey, onOpenContextMenu]);

  return (
    <article
      ref={measureElement}
      data-message-key={messageDomKey}
      className={cx(
        "group w-full",
        isHighlighted && "message-hit-anchor",
        isUser && "text-right",
      )}
      style={{ contentVisibility: "auto", containIntrinsicSize: "0 120px" }}
      onContextMenu={openContextMenu}
    >
      <div className={cx("message-row flex w-full items-start gap-3", isUser && "flex-row-reverse justify-start")}>
        {!isUser ? (
          activeRole?.avatar_abs ? (
            <img
              className={agentAvatarClass}
              src={toFileUrl(activeRole.avatar_abs)}
              alt={`${activeRole.name} avatar`}
            />
          ) : (
            <span className={cx(agentAvatarClass, "text-xs font-bold text-accent-deep")}>
              {activeRole ? activeRole.name.slice(0, 1).toUpperCase() : "A"}
            </span>
          )
        ) : null}
        <div className={cx("message-body flex min-w-0 w-full max-w-[82%] flex-col text-sm leading-6 text-[#1f1f1f]", isUser && "ml-auto items-end")}>
          {!isUser ? (
            <div className={cx("message-author mb-1 font-medium leading-none text-[#b9b9b9]", chatMinorTextClass)}>
              {authorLabel}
            </div>
          ) : null}
          <div className={cx(
            bubbleClass,
            !message.content
              && !storedReplyPreview
              && !isStreaming
              && !thinking
              && !hasToolCalls
              && !presentation.hasIntermediateNarrative
              && "hidden",
            isHighlighted && "message-bubble-highlight ring-2 ring-[#111827]/10",
          )}>
            {storedReplyPreview ? (
              storedReplyPreview.messageId ? (
                <button
                  className="mb-2 block max-w-[420px] border-0 bg-transparent p-0 text-left transition hover:opacity-85 focus:outline-none"
                  type="button"
                  aria-label="跳转到被引用消息"
                  onClick={() => onJumpToMessage(storedReplyPreview.messageId)}
                >
                  <div className="border-l-2 border-[#AEB7C5] pl-2.5">
                    {storedReplyPreview.sender ? (
                      <div className="truncate text-[11px] font-medium leading-4 text-[#6B7280]">{storedReplyPreview.sender}</div>
                    ) : null}
                    <div className="line-clamp-2 text-[12px] leading-5 text-[#7B8190]">{storedReplyPreview.preview}</div>
                  </div>
                </button>
              ) : (
                <div className="mb-2 max-w-[420px] border-l-2 border-[#AEB7C5] pl-2.5 text-left">
                  {storedReplyPreview.sender ? (
                    <div className="truncate text-[11px] font-medium leading-4 text-[#6B7280]">{storedReplyPreview.sender}</div>
                  ) : null}
                  <div className="line-clamp-2 text-[12px] leading-5 text-[#7B8190]">{storedReplyPreview.preview}</div>
                </div>
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
                {isStreaming && (message.content || !thinking) ? <span className="chat-stream-cursor ml-0.5" aria-hidden="true" /> : null}
              </div>
            ) : (
              <>
                <ChatMarkdownContent content={message.content} />
                {isStreaming && (message.content || !thinking) ? <span className="chat-stream-cursor ml-0.5" aria-hidden="true" /> : null}
              </>
            )}
            {!isStreaming ? <ChatReplyMetrics metrics={turnMetrics} hasThinking={Boolean(thinking)} /> : null}
          </div>
          <ChatMessageAttachments
            messageKey={messageDomKey}
            media={message.media}
            onBeginAttachmentDrag={onBeginAttachmentDrag}
            onOpenImagePreview={onOpenImagePreview}
          />
          {message.timestamp || sourceLabel ? (
            <div className={cx("message-time mt-1 flex items-center gap-2 text-muted opacity-0 transition-opacity duration-150 group-hover:opacity-100", chatMinorTextClass)}>
              {message.timestamp ? <span>{formatTimestamp(message.timestamp)}</span> : null}
              {sourceLabel ? <span>{`from ${sourceLabel.toLowerCase()}`}</span> : null}
            </div>
          ) : null}
        </div>
      </div>
    </article>
  );
});
