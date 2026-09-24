import React from "react";
import { ChatMessageRow, type ChatMessageActionHandlers } from "./ChatMessageRow";
import { useChatMessageVirtualization } from "./useChatMessageVirtualization";
import { getChatMessageDomKey, getChatMessageReactKey } from "./chatMessageIdentity";
import type { getVisibleChatMessages } from "./chatMessageWindow";
import type { RoleChannelCatalog } from "../roles/roleChannelCatalog";
import { cx } from "../shared/styles";
import type { RoleRecord, SessionMessage } from "../shared/types";

type ChatMessageListProps = Partial<ChatMessageActionHandlers> & {
  activeRole: RoleRecord | null;
  sessionKey?: string;
  conversationEndRef: React.RefObject<HTMLDivElement | null>;
  conversationListRef: React.RefObject<HTMLDivElement | null>;
  highlightedMessageKey: string;
  onMessageNavigationTargetMounted?: (messageKey: string, target: HTMLElement) => void;
  isAutoScrollingRef?: React.RefObject<boolean>;
  visibleMessageWindow: ReturnType<typeof getVisibleChatMessages>;
  /** Render keys of rows appended after mount that should play the enter animation. */
  enteringKeys?: ReadonlySet<string>;
  /** Render key of the latest failed turn's error row, when it can be retried. */
  retryableKey?: string;
  sending?: boolean;
  channelCatalog?: RoleChannelCatalog;
  onBeginAttachmentDrag: (path: string) => void;
  onContentSizeChange?: () => void;
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
const noEnteringKeys: ReadonlySet<string> = new Set();
const noop = () => undefined;

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
  enteringKeys = noEnteringKeys,
  retryableKey = "",
  sending = false,
  channelCatalog = null,
  onBeginAttachmentDrag,
  onContentSizeChange,
  onJumpToMessage,
  onOpenContextMenu,
  onOpenImagePreview,
  onCopyMessage = noop,
  onQuoteMessage = noop,
  onRetryMessage = noop,
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
        {virtualMessageWindow.ranges.flatMap((range) => [
          ...(range.spacerHeightBefore > 0 ? [
            <div key={`spacer:${range.startIndex}`} aria-hidden="true" className="pointer-events-none" style={{ height: range.spacerHeightBefore }} />,
          ] : []),
          ...range.messages.map((message, visibleIndex) => {
            const index = visibleMessageWindow.startIndex + range.startIndex + visibleIndex;
            const renderKey = getChatMessageReactKey(message, index);
            return (
              <ChatMessageRow
                key={renderKey}
                activeRole={activeRole}
                index={index}
                renderKey={renderKey}
                isHighlighted={getChatMessageDomKey(message, index) === highlightedMessageKey}
                message={message}
                animateEnter={enteringKeys.has(renderKey)}
                sending={sending}
                retryable={renderKey === retryableKey}
                channelCatalog={channelCatalog}
                onBeginAttachmentDrag={onBeginAttachmentDrag}
                onJumpToMessage={onJumpToMessage}
                onMeasureElement={observeMessageElement}
                onOpenContextMenu={onOpenContextMenu}
                onOpenImagePreview={onOpenImagePreview}
                onCopyMessage={onCopyMessage}
                onQuoteMessage={onQuoteMessage}
                onRetryMessage={onRetryMessage}
              />
            );
          }),
        ])}
        {virtualMessageWindow.bottomSpacerHeight > 0 ? (
          <div aria-hidden="true" className="pointer-events-none" style={{ height: virtualMessageWindow.bottomSpacerHeight }} />
        ) : null}
        {/* Keeps the newest message clear of the floating composer, whatever its current height. */}
        <div ref={conversationEndRef} style={{ height: "var(--chat-composer-clearance, 160px)" }} />
      </div>
    </div>
  );
});
