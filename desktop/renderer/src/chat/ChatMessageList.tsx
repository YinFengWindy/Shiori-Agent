import React from "react";
import { ChatMessageImage } from "./ChatMessageImage";
import {
  getChatAttachmentName,
  getChatMessageSourceLabel,
  getStoredChatReplyPreview,
} from "./chatMessageActions";
import { buildChatImageHistoryKey, isChatImageAsset } from "./chatImageHistory";
import { normalizeSessionMediaPaths } from "./chatMedia";
import { getChatMessageDomKey, getChatMessageReactKey } from "./chatMessageIdentity";
import type { getVisibleChatMessages } from "./chatMessageWindow";
import { formatTimestamp, toFileUrl } from "../shared/format";
import { DocumentIcon } from "../shared/icons";
import { cx, focusResetClass } from "../shared/styles";
import type { RoleRecord, SessionMessage } from "../shared/types";

type ChatMessageListProps = {
  activeRole: RoleRecord | null;
  conversationEndRef: React.RefObject<HTMLDivElement | null>;
  conversationListRef: React.RefObject<HTMLDivElement | null>;
  highlightedMessageKey: string;
  visibleMessageWindow: ReturnType<typeof getVisibleChatMessages>;
  onBeginAttachmentDrag: (path: string) => void;
  onExpandOlderMessages: () => void;
  onJumpToMessage: (messageKey: string) => void;
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
const chatBodyClass = "text-sm leading-6";
const chatMinorTextClass = "text-[12px]";
const chatContentTrackClass = "mx-auto w-full max-w-[860px] px-5 md:px-6";
const assistantMessageBubbleClass =
  "message-bubble w-fit max-w-full rounded-[14px] border border-[rgba(228,228,228,0.66)] bg-[rgba(255,255,255,0.48)] px-3.5 py-2.5 text-left shadow-[0_1px_2px_rgba(0,0,0,0.03)] backdrop-blur-[10px] transition-colors duration-150 group-hover:bg-[rgba(255,255,255,0.72)]";
const userMessageBubbleClass =
  "message-bubble w-fit max-w-full rounded-[14px] border border-[#E4E4E4] bg-white px-3.5 py-2.5 text-left shadow-[0_1px_2px_rgba(0,0,0,0.04)]";

/** Renders the current chat message window and its attachments. */
export const ChatMessageList = React.memo(function ChatMessageList({
  activeRole,
  conversationEndRef,
  conversationListRef,
  highlightedMessageKey,
  visibleMessageWindow,
  onBeginAttachmentDrag,
  onExpandOlderMessages,
  onJumpToMessage,
  onOpenContextMenu,
  onOpenImagePreview,
}: ChatMessageListProps) {
  function handleAttachmentDragStart(event: React.DragEvent<HTMLElement>, path: string): void {
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.effectAllowed = "copy";
    onBeginAttachmentDrag(path);
  }

  return (
    <div
      ref={conversationListRef}
      className={cx(
        "conversation-list scrollbar-soft scrollbar-soft-muted relative z-[1] h-full min-h-0 overflow-auto pb-5 pt-7",
        chatBodyClass,
      )}
    >
      <div className={cx("grid content-start gap-3", chatContentTrackClass)}>
        {visibleMessageWindow.hiddenMessageCount > 0 ? (
          <div className="flex justify-center">
            <button
              className={cx(
                "rounded-md border border-[#D8DEE8] bg-white/85 px-3 py-1.5 text-[12px] text-[#5B6472] transition hover:border-[#C6CEDA] hover:bg-white",
                focusResetClass,
              )}
              type="button"
              onClick={onExpandOlderMessages}
            >
              {`更早消息 ${visibleMessageWindow.hiddenMessageCount} 条`}
            </button>
          </div>
        ) : null}
        {visibleMessageWindow.messages.map((message, visibleIndex) => {
          const index = visibleMessageWindow.startIndex + visibleIndex;
          const isUser = message.role === "user";
          const isError = message.role === "error";
          const authorLabel = isError ? "系统提示" : (isUser ? "你" : (activeRole?.name || "Agent"));
          const messageReactKey = getChatMessageReactKey(message, index);
          const messageDomKey = getChatMessageDomKey(message, index);
          const isHighlighted = highlightedMessageKey === messageDomKey;
          const sourceLabel = getChatMessageSourceLabel(message);
          const media = normalizeSessionMediaPaths(message.media);
          const storedReplyPreview = getStoredChatReplyPreview(message);
          const bubbleClass = isError
            ? "message-bubble w-fit max-w-full rounded-[14px] border border-[rgba(176,58,58,0.22)] bg-[rgba(255,244,244,0.96)] px-3.5 py-2.5 text-left text-[#8f2d2d] shadow-[0_1px_2px_rgba(0,0,0,0.04)]"
            : isUser
              ? userMessageBubbleClass
              : assistantMessageBubbleClass;

          return (
            <article
              key={messageReactKey}
              data-message-key={messageDomKey}
              className={cx(
                "group w-full",
                isHighlighted && "message-hit-anchor",
                isUser && "text-right",
              )}
              onContextMenu={(event) => onOpenContextMenu(event, message, messageDomKey, authorLabel)}
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
                    !message.content && !storedReplyPreview && "hidden",
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
                    <div className="message-content whitespace-pre-wrap break-words">{message.content}</div>
                  </div>
                  {media.length ? (
                    <div className="mt-2 grid gap-2" data-message-media="separate">
                      {media.map((item, mediaIndex) => (
                        isChatImageAsset(item) ? (
                          <button
                            key={`${messageDomKey}:${mediaIndex}:${item}`}
                            className="block w-fit max-w-full cursor-grab overflow-hidden rounded-[12px] border border-black/8 bg-white/70 p-0 text-left transition hover:bg-white active:cursor-grabbing focus:outline-none"
                            type="button"
                            draggable
                            onDragStart={(event) => handleAttachmentDragStart(event, item)}
                            onClick={() => onOpenImagePreview(buildChatImageHistoryKey(messageDomKey, mediaIndex))}
                          >
                            <ChatMessageImage imagePath={item} />
                          </button>
                        ) : (
                          <a
                            key={`${messageDomKey}:${mediaIndex}:${item}`}
                            href={toFileUrl(item)}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex max-w-[280px] cursor-grab items-center gap-2.5 rounded-full border border-black/8 bg-[#F7F7F8] px-3 py-2 text-[12px] text-[#1F2937] transition hover:bg-white active:cursor-grabbing focus:outline-none"
                            draggable
                            onDragStart={(event) => handleAttachmentDragStart(event, item)}
                          >
                            <span className="grid h-6 w-6 flex-none place-items-center rounded-full bg-transparent text-[#8B95A7]">
                              <DocumentIcon className="h-[13px] w-[13px] stroke-current" />
                            </span>
                            <span className="truncate font-medium">{getChatAttachmentName(item)}</span>
                          </a>
                        )
                      ))}
                    </div>
                  ) : null}
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
        })}
        <div ref={conversationEndRef} className="h-40" />
      </div>
    </div>
  );
});
