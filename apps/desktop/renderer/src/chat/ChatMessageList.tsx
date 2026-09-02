import React from "react";
import { ChatMessageRow } from "./ChatMessageRow";
import { useChatMessageVirtualization } from "./useChatMessageVirtualization";
import { getChatMessageDomKey, getChatMessageReactKey } from "./chatMessageIdentity";
import type { getVisibleChatMessages } from "./chatMessageWindow";
import { cx, focusResetClass } from "../shared/styles";
import type { RoleRecord, SessionMessage } from "../shared/types";

type ChatMessageListProps = {
  activeRole: RoleRecord | null;
  sessionKey?: string;
  conversationEndRef: React.RefObject<HTMLDivElement | null>;
  conversationListRef: React.RefObject<HTMLDivElement | null>;
  highlightedMessageKey: string;
  onMessageNavigationTargetMounted?: (messageKey: string, target: HTMLElement) => void;
  isAutoScrollingRef?: React.RefObject<boolean>;
  visibleMessageWindow: ReturnType<typeof getVisibleChatMessages>;
  canLoadOlderMessages?: boolean;
  loadingOlderMessages?: boolean;
  onBeginAttachmentDrag: (path: string) => void;
  onContentSizeChange?: () => void;
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

const chatBodyClass = "text-sm leading-6";
const chatContentTrackClass = "mx-auto w-full max-w-[860px] px-5 md:px-6";

/** Renders the current chat message window and its attachments. */
export const ChatMessageList = React.memo(function ChatMessageList({
  activeRole,
  sessionKey = "",
  conversationEndRef,
  conversationListRef,
  highlightedMessageKey,
  onMessageNavigationTargetMounted,
  isAutoScrollingRef,
  visibleMessageWindow,
  canLoadOlderMessages = visibleMessageWindow.hiddenMessageCount > 0,
  loadingOlderMessages = false,
  onBeginAttachmentDrag,
  onContentSizeChange,
  onExpandOlderMessages,
  onJumpToMessage,
  onOpenContextMenu,
  onOpenImagePreview,
}: ChatMessageListProps) {
  const fallbackAutoScrollingRef = React.useRef(false);
  const { virtualMessageWindow, observeMessageElement } = useChatMessageVirtualization({
    sessionKey,
    messages: visibleMessageWindow.messages,
    messageStartIndex: visibleMessageWindow.startIndex,
    highlightedMessageKey,
    conversationListRef,
    onMessageNavigationTargetMounted,
    isAutoScrollingRef: isAutoScrollingRef ?? fallbackAutoScrollingRef,
    onContentSizeChange,
  });

  return (
    <div
      ref={conversationListRef}
      className={cx(
        "conversation-list scrollbar-soft scrollbar-soft-muted relative z-[1] h-full min-h-0 overflow-auto pb-5 pt-7",
        chatBodyClass,
      )}
      style={{ overflowAnchor: "none" }}
    >
      <div className={cx("grid content-start gap-3", chatContentTrackClass)}>
        {canLoadOlderMessages ? (
          <div className="flex justify-center">
            <button
              className={cx(
                "rounded-md border border-[#D8DEE8] bg-white/85 px-3 py-1.5 text-[12px] text-[#5B6472] transition hover:border-[#C6CEDA] hover:bg-white",
                focusResetClass,
              )}
              type="button"
              disabled={loadingOlderMessages}
              onClick={onExpandOlderMessages}
            >
              {loadingOlderMessages ? "正在加载更早消息" : `更早消息 ${visibleMessageWindow.hiddenMessageCount} 条`}
            </button>
          </div>
        ) : null}
        {virtualMessageWindow.topSpacerHeight > 0 ? (
          <div aria-hidden="true" className="pointer-events-none" style={{ height: virtualMessageWindow.topSpacerHeight }} />
        ) : null}
        {virtualMessageWindow.messages.map((message, visibleIndex) => {
          const index = visibleMessageWindow.startIndex + virtualMessageWindow.startIndex + visibleIndex;
          return (
            <ChatMessageRow
              key={getChatMessageReactKey(message, index)}
              activeRole={activeRole}
              index={index}
              isHighlighted={getChatMessageDomKey(message, index) === highlightedMessageKey}
              message={message}
              onBeginAttachmentDrag={onBeginAttachmentDrag}
              onJumpToMessage={onJumpToMessage}
              onMeasureElement={observeMessageElement}
              onOpenContextMenu={onOpenContextMenu}
              onOpenImagePreview={onOpenImagePreview}
            />
          );
        })}
        {virtualMessageWindow.bottomSpacerHeight > 0 ? (
          <div aria-hidden="true" className="pointer-events-none" style={{ height: virtualMessageWindow.bottomSpacerHeight }} />
        ) : null}
        <div ref={conversationEndRef} className="h-40" />
      </div>
    </div>
  );
});
