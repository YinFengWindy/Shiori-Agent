import React, { useCallback, useEffect, useEffectEvent, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ChatComposer, type ChatComposerDraftRequest } from "./ChatComposer";
import { chatComposerBottomOffsetPx } from "./chatComposerLayout";
import { ChatEmptyState } from "./ChatEmptyState";
import { ChatHeader } from "./ChatHeader";
import { ChatMessageContextMenu } from "./ChatMessageContextMenu";
import { ChatMessageList } from "./ChatMessageList";
import {
  getChatMessageActionAvailability,
  getChatMessageCopyText,
  getChatMessageReplyContent,
} from "./chatMessageActions";
import { findRetryableChatErrorKey } from "./chatFailedTurn";
import { getChatMessageReactKey } from "./chatMessageIdentity";
import { ChatRightSidebar, type ChatSidebarMode } from "./ChatRightSidebar";
import { ChatPanelToggle, ChatPanelSegments } from "./ChatPanelControls";
import {
  clearViewedChatPanelBadge,
  emptyChatPanelBadges,
  markChatPanelUpdates,
  shouldBadgeChatPanelToggle,
  type ChatPanelBadges,
} from "./chatPanelBadges";
import {
  shouldAutoScrollOnNewMessage,
} from "./chatAutoScroll";
import { shouldLoadOlderChatMessagesAfterSessionRestore } from "./chatMessagePaginationState";
import { summarizeChatReplyContent } from "./chatComposerState";
import { ChatScrollToBottomButton } from "./ChatScrollToBottomButton";
import { ChatSurfaceBackdrop } from "./ChatSurfaceBackdrop";
import { useRoleTasks } from "./useRoleTasks";
import { useChatMessageContextMenu } from "./useChatMessageContextMenu";
import { useChatMessageEnterKeys } from "./useChatMessageEnterKeys";
import { useChatMessagePagination } from "./useChatMessagePagination";
import { useChatBottomFollow } from "./useChatBottomFollow";
import {
  type ChatMessageNavigationScroller,
  useChatScrollController,
} from "./useChatScrollController";
import { useRoleChannelCatalog } from "../roles/useRoleChannelCatalog";
import { cx, sidebarContentMotionClass, sidebarTrackMotionClass } from "../shared/styles";
import { useLatestRef } from "../shared/useLatestRef";
import type { ChatReplyTarget, ChatSendRequest, RoleRecord, SessionMessage, SessionPayload } from "../shared/types";

type ChatSurfaceProps = {
  activeRole: RoleRecord | null;
  activeRoleId: string;
  activeSession: SessionPayload | null;
  bridgeReady: boolean;
  chatLatestImagePath: string;
  chatLatestImagePosition: number;
  chatLatestImageSidebarAnimating: boolean;
  chatLatestImageSidebarResizing: boolean;
  chatLatestImageSidebarCollapsed: boolean;
  chatLatestImageSidebarCount: number;
  chatLatestImageSidebarWidth: number;
  currentMood: string;
  moodIllustrationUrl: string;
  roleSelfView: string;
  relationshipTags: string[];
  lonelinessValue: number;
  conversationEndRef: React.RefObject<HTMLDivElement | null>;
  headerTitle: string;
  highlightedMessageKey: string;
  onMessageNavigationTargetMounted?: (
    messageKey: string,
    target: HTMLElement,
    scrollToMessage: ChatMessageNavigationScroller,
  ) => void;
  sending: boolean;
  cancelling: boolean;
  visibleIllustrationUrl: string;
  windowVisible: boolean;
  onBeginChatLatestImageSidebarResize: (event: React.PointerEvent<HTMLDivElement>) => void;
  onGoToNextChatImage: () => void;
  onGoToPreviousChatImage: () => void;
  onOpenChatImageLightbox: () => void;
  onOpenChatImagePreview: (target: { historyKey: string }) => void;
  onOpenRoleDetail: () => void;
  onJumpToMessage: (messageKey: string) => void;
  onBeginAttachmentDrag: (path: string) => void;
  onCopyMessage: (content: string) => void;
  onSendMessage: (request: ChatSendRequest) => Promise<boolean>;
  onCancelChat: () => void;
  /** Re-sends the user message of the failed turn ending in this error row (render key). */
  onRetryFailedTurn?: (errorKey: string) => void;
  onLoadOlderMessages?: (sessionKey: string) => Promise<boolean>;
  onToggleChatLatestImageSidebar: () => void;
};

const emptySessionMessages: SessionMessage[] = [];

/** Room kept between the composer's top and the newest message when scrolled to the bottom. */
const composerClearanceGapPx = 24;

/** Renders the active role chat header, conversation messages, and composer. */
export function ChatSurface({
  activeRole,
  activeRoleId,
  activeSession,
  bridgeReady,
  chatLatestImagePath,
  chatLatestImagePosition,
  chatLatestImageSidebarAnimating,
  chatLatestImageSidebarResizing,
  chatLatestImageSidebarCollapsed,
  chatLatestImageSidebarCount,
  chatLatestImageSidebarWidth,
  currentMood,
  moodIllustrationUrl,
  roleSelfView,
  relationshipTags,
  lonelinessValue,
  conversationEndRef,
  headerTitle,
  highlightedMessageKey,
  onMessageNavigationTargetMounted,
  sending,
  cancelling,
  visibleIllustrationUrl,
  windowVisible,
  onBeginChatLatestImageSidebarResize,
  onGoToNextChatImage,
  onGoToPreviousChatImage,
  onOpenChatImageLightbox,
  onOpenChatImagePreview,
  onOpenRoleDetail,
  onJumpToMessage,
  onBeginAttachmentDrag,
  onCopyMessage,
  onSendMessage,
  onCancelChat,
  onRetryFailedTurn = () => undefined,
  onLoadOlderMessages = async () => false,
  onToggleChatLatestImageSidebar,
}: ChatSurfaceProps) {
  const [visualsActive, setVisualsActive] = useState(() => (
    typeof document === "undefined" ? true : !document.hidden
  ));
  const conversationPanelRef = useRef<HTMLElement | null>(null);
  const conversationListRef = useRef<HTMLDivElement | null>(null);
  const previousMessageCountRef = useRef(0);
  const previousLastMessageContentRef = useRef("");
  const previousChatImageCountRef = useRef(0);
  const previousRoleSelfViewRef = useRef(roleSelfView);
  const [panelBadges, setPanelBadges] = useState<ChatPanelBadges>(emptyChatPanelBadges);
  const highlightedMessageKeyRef = useLatestRef(highlightedMessageKey);
  const [chatLatestImageSidebarMounted, setChatLatestImageSidebarMounted] = useState(!chatLatestImageSidebarCollapsed);
  const messageContextMenu = useChatMessageContextMenu();
  const [composerReplyTarget, setComposerReplyTarget] = useState<ChatReplyTarget | null>(null);
  const [composerDraftRequest, setComposerDraftRequest] = useState<ChatComposerDraftRequest | null>(null);
  const [conversationPaneHeight, setConversationPaneHeight] = useState(0);
  const channelCatalog = useRoleChannelCatalog();
  const hasStatusIllustration = Boolean(moodIllustrationUrl);
  const hasStatusContent = hasStatusIllustration || Boolean(roleSelfView);
  const [sidebarMode, setSidebarMode] = useState<ChatSidebarMode>(
    hasStatusContent ? "status" : "images",
  );
  const roleTasks = useRoleTasks({
    activeRoleId,
    bridgeReady,
    enabled: sidebarMode === "tasks" && !chatLatestImageSidebarCollapsed,
  });
  const sessionMessages = activeSession?.messages ?? emptySessionMessages;
  const currentLastMessageContent = sessionMessages.at(-1)?.content ?? "";
  const enteringMessageKeys = useChatMessageEnterKeys(activeSession?.key ?? "", sessionMessages);
  const retryableMessageKey = useMemo(() => findRetryableChatErrorKey(sessionMessages), [sessionMessages]);
  const {
    visibleMessageWindow,
    canLoadOlderMessages,
    loading: loadingOlderMessages,
    maybeLoadOlderMessages,
  } = useChatMessagePagination({
    activeSession,
    conversationListRef,
    highlightedMessageKey,
    loadOlderMessages: onLoadOlderMessages,
  });
  const {
    isAutoScrollingRef,
    restoreSessionScroll,
    cancelScroll,
    scrollToBottom,
    scrollToMessage,
  } = useChatScrollController({
    conversationListRef,
    sessionKey: activeSession?.key ?? "",
  });
  const handleMessageNavigationTargetMounted = useCallback((messageKey: string, target: HTMLElement) => {
    onMessageNavigationTargetMounted?.(messageKey, target, scrollToMessage);
  }, [onMessageNavigationTargetMounted, scrollToMessage]);
  const { stickToBottomRef, scrollState, scrollConversationToBottom, handleChatContentSizeChange } = useChatBottomFollow({
    conversationListRef,
    isAutoScrollingRef,
    sessionKey: activeSession?.key ?? "",
    highlightedMessageKey,
    scrollToBottom,
    cancelScroll,
    maybeLoadOlderMessages,
  });
  const resetConversationForSession = useEffectEvent(() => {
    const sessionKey = activeSession?.key ?? "";
    previousMessageCountRef.current = activeSession?.messages.length ?? 0;
    previousLastMessageContentRef.current = activeSession?.messages.at(-1)?.content ?? "";
    previousChatImageCountRef.current = chatLatestImageSidebarCount;
    previousRoleSelfViewRef.current = roleSelfView;
    setPanelBadges(emptyChatPanelBadges);
    const hasPendingMessageNavigation = Boolean(highlightedMessageKeyRef.current);
    const container = conversationListRef.current;
    if (hasPendingMessageNavigation) {
      stickToBottomRef.current = false;
      return;
    }
    if (!container) return;
    const restoredSessionScroll = restoreSessionScroll(sessionKey);
    if (restoredSessionScroll) {
      stickToBottomRef.current = restoredSessionScroll.wasAtBottom;
      if (shouldLoadOlderChatMessagesAfterSessionRestore({
        scrollTop: container.scrollTop,
        restoredWasAtBottom: restoredSessionScroll.wasAtBottom,
        canLoadOlderMessages,
        loading: loadingOlderMessages,
      })) {
        maybeLoadOlderMessages(container.scrollTop, false);
      }
      return;
    }
    stickToBottomRef.current = true;
    scrollConversationToBottom("auto");
  });

  useEffect(() => {
    if (typeof document === "undefined") {
      return undefined;
    }

    const updateVisualsActive = () => {
      setVisualsActive((current) => {
        const next = !document.hidden;
        return current === next ? current : next;
      });
    };

    updateVisualsActive();
    document.addEventListener("visibilitychange", updateVisualsActive);
    window.addEventListener("focus", updateVisualsActive);
    window.addEventListener("blur", updateVisualsActive);

    return () => {
      document.removeEventListener("visibilitychange", updateVisualsActive);
      window.removeEventListener("focus", updateVisualsActive);
      window.removeEventListener("blur", updateVisualsActive);
    };
  }, []);

  useEffect(() => {
    if (!chatLatestImageSidebarCollapsed) {
      setChatLatestImageSidebarMounted(true);
      return undefined;
    }
    const timer = window.setTimeout(() => setChatLatestImageSidebarMounted(false), 240);
    return () => window.clearTimeout(timer);
  }, [chatLatestImageSidebarCollapsed]);

  useEffect(() => {
    if (hasStatusContent || sidebarMode !== "status") {
      return;
    }
    setSidebarMode("images");
  }, [hasStatusContent, sidebarMode]);

  // The composer's max height follows the pane it floats in.
  useEffect(() => {
    const panel = conversationPanelRef.current;
    if (!panel || typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(() => {
      setConversationPaneHeight((current) => current === panel.clientHeight ? current : panel.clientHeight);
    });
    observer.observe(panel);
    return () => observer.disconnect();
  }, []);

  useLayoutEffect(() => {
    resetConversationForSession();
  }, [activeSession?.key]);

  // New images / a new thought mark their segment instead of opening the
  // panel or switching its segment under the user.
  const panelOpen = !chatLatestImageSidebarCollapsed;
  useEffect(() => {
    const previousImageCount = previousChatImageCountRef.current;
    const previousRoleSelfView = previousRoleSelfViewRef.current;
    previousChatImageCountRef.current = chatLatestImageSidebarCount;
    previousRoleSelfViewRef.current = roleSelfView;
    const update = {
      newImage: chatLatestImageSidebarCount > previousImageCount,
      newThought: Boolean(roleSelfView) && roleSelfView !== previousRoleSelfView,
    };
    if (!update.newImage && !update.newThought) return;
    setPanelBadges((current) => markChatPanelUpdates(current, update, { open: panelOpen, mode: sidebarMode }));
  }, [chatLatestImageSidebarCount, panelOpen, roleSelfView, sidebarMode]);

  useEffect(() => {
    setPanelBadges((current) => clearViewedChatPanelBadge(current, { open: panelOpen, mode: sidebarMode }));
  }, [panelOpen, sidebarMode]);

  useEffect(() => {
    setComposerReplyTarget(null);
    setComposerDraftRequest(null);
  }, [activeRoleId, activeSession?.key]);

  useEffect(() => {
    const currentMessageCount = activeSession?.messages.length ?? 0;
    const previousMessageCount = previousMessageCountRef.current;
    const previousLastMessageContent = previousLastMessageContentRef.current;
    previousMessageCountRef.current = currentMessageCount;
    previousLastMessageContentRef.current = currentLastMessageContent;
    if (!shouldAutoScrollOnNewMessage({
      currentMessageCount,
      previousMessageCount,
      lastMessageContent: currentLastMessageContent,
      previousLastMessageContent,
      highlightedMessageKey,
      sending,
      wasAtBottom: stickToBottomRef.current,
    })) {
      return;
    }
    scrollConversationToBottom("auto");
  }, [activeSession?.messages.length, currentLastMessageContent, highlightedMessageKey, scrollConversationToBottom, sending, stickToBottomRef]);

  const renderHeavyVisuals = visualsActive && windowVisible;
  const hasIllustration = Boolean(visibleIllustrationUrl) && renderHeavyVisuals;
  const showScrollToBottom = scrollState.isScrollable && !scrollState.isAtBottom;
  const hasChatImageHistory = chatLatestImageSidebarCount > 0;
  const canGoToPreviousChatImage = chatLatestImagePosition > 1;
  const canGoToNextChatImage = hasChatImageHistory && chatLatestImagePosition < chatLatestImageSidebarCount;
  const canOpenRoleDetail = Boolean(activeRole && activeRoleId);
  const detailRole = canOpenRoleDetail ? activeRole : null;
  const showEmptyState = Boolean(activeRole && activeSession && !sessionMessages.length && !canLoadOlderMessages);

  const handleScrollToBottom = () => {
    scrollConversationToBottom("smooth");
    stickToBottomRef.current = true;
  };

  const handleOpenChatImagePreview = useCallback((historyKey: string) => {
    setSidebarMode("images");
    onOpenChatImagePreview({ historyKey });
  }, [onOpenChatImagePreview]);

  const handleOpenRoleDetail = useCallback(() => {
    if (!canOpenRoleDetail) return;
    onOpenRoleDetail();
  }, [canOpenRoleDetail, onOpenRoleDetail]);

  const handleClearReplyTarget = useCallback(() => {
    setComposerReplyTarget(null);
  }, []);

  // The list's bottom spacer and the scroll-to-bottom button track the
  // composer's live height (it grows with the draft, quote and attachments);
  // a follower stays pinned to the newest message while it grows.
  const handleComposerHeightChange = useCallback((height: number) => {
    const panel = conversationPanelRef.current;
    if (!panel) return;
    panel.style.setProperty("--chat-composer-height", `${height}px`);
    panel.style.setProperty("--chat-composer-clearance", `${height + chatComposerBottomOffsetPx + composerClearanceGapPx}px`);
    if (stickToBottomRef.current) scrollConversationToBottom("auto");
  }, [scrollConversationToBottom, stickToBottomRef]);

  const handleCopyMessage = useCallback((message: SessionMessage) => {
    onCopyMessage(getChatMessageCopyText(message));
  }, [onCopyMessage]);

  const handleQuoteMessage = useCallback((message: SessionMessage, messageKey: string, sender: string) => {
    const content = getChatMessageReplyContent(message);
    if (!content) return;
    setComposerReplyTarget({
      messageId: messageKey,
      content,
      sender,
      preview: summarizeChatReplyContent(content),
    });
  }, []);

  const handlePickSuggestion = useCallback((text: string) => {
    setComposerDraftRequest((current) => ({ text, id: (current?.id ?? 0) + 1 }));
  }, []);

  const contextMenuState = messageContextMenu.menu;
  const contextMenuRenderKey = contextMenuState
    ? getChatMessageReactKey(contextMenuState.message, sessionMessages.indexOf(contextMenuState.message))
    : "";

  return (
    <section className="chat-surface relative grid h-full min-h-0 grid-cols-[minmax(0,1fr)_auto] overflow-hidden bg-gradient-app bg-fixed">
      <ChatPanelToggle
        open={panelOpen}
        badged={shouldBadgeChatPanelToggle(panelBadges, panelOpen)}
        onToggle={onToggleChatLatestImageSidebar}
      />
      {contextMenuState ? (
        <ChatMessageContextMenu
          menu={contextMenuState}
          menuRef={messageContextMenu.menuRef}
          availability={getChatMessageActionAvailability(contextMenuState.message, {
            sending,
            retryable: contextMenuRenderKey === retryableMessageKey,
          })}
          onCopy={() => {
            handleCopyMessage(contextMenuState.message);
            messageContextMenu.close();
          }}
          onQuote={() => {
            handleQuoteMessage(contextMenuState.message, contextMenuState.messageKey, contextMenuState.sender);
            messageContextMenu.close();
          }}
          onRetry={() => {
            onRetryFailedTurn(contextMenuRenderKey);
            messageContextMenu.close();
          }}
        />
      ) : null}
      <div className="relative grid h-full min-h-0 grid-rows-chat overflow-hidden">
      {hasIllustration ? <ChatSurfaceBackdrop url={visibleIllustrationUrl} /> : null}
      <ChatHeader
        activeRole={activeRole}
        detailRole={detailRole}
        title={headerTitle}
        typing={sending}
        onOpenRoleDetail={handleOpenRoleDetail}
      />
      <section ref={conversationPanelRef} className="conversation-panel relative z-[1] h-full min-h-0 overflow-hidden bg-transparent">
        <ChatMessageList
          activeRole={activeRole}
          sessionKey={activeSession?.key ?? ""}
          conversationEndRef={conversationEndRef}
          conversationListRef={conversationListRef}
          highlightedMessageKey={highlightedMessageKey}
          onMessageNavigationTargetMounted={handleMessageNavigationTargetMounted}
          isAutoScrollingRef={isAutoScrollingRef}
          visibleMessageWindow={visibleMessageWindow}
          enteringKeys={enteringMessageKeys}
          retryableKey={retryableMessageKey}
          sending={sending}
          channelCatalog={channelCatalog}
          onBeginAttachmentDrag={onBeginAttachmentDrag}
          onContentSizeChange={handleChatContentSizeChange}
          onJumpToMessage={onJumpToMessage}
          onOpenContextMenu={messageContextMenu.open}
          onOpenImagePreview={handleOpenChatImagePreview}
          onCopyMessage={handleCopyMessage}
          onQuoteMessage={handleQuoteMessage}
          onRetryMessage={onRetryFailedTurn}
        />
        {showEmptyState && activeRole ? (
          <ChatEmptyState role={activeRole} onPickSuggestion={handlePickSuggestion} />
        ) : null}
        {showScrollToBottom ? <ChatScrollToBottomButton onClick={handleScrollToBottom} /> : null}
        <ChatComposer
          activeRoleId={activeRoleId}
          sessionKey={activeSession?.key ?? ""}
          bridgeReady={bridgeReady}
          sending={sending}
          cancelling={cancelling}
          replyTarget={composerReplyTarget}
          paneHeight={conversationPaneHeight}
          draftRequest={composerDraftRequest}
          onSendMessage={onSendMessage}
          onCancelChat={onCancelChat}
          onClearReplyTarget={handleClearReplyTarget}
          onJumpToMessage={onJumpToMessage}
          onHeightChange={handleComposerHeightChange}
        />
      </section>
      </div>
      <div
        className={cx(
          "relative h-full overflow-hidden border-l border-line-soft bg-gradient-app bg-fixed",
          chatLatestImageSidebarAnimating && sidebarTrackMotionClass,
          chatLatestImageSidebarResizing && !chatLatestImageSidebarAnimating && "transition-[width] duration-100 ease-out",
        )}
        style={{ width: chatLatestImageSidebarCollapsed ? 0 : chatLatestImageSidebarWidth }}
      >
        {!chatLatestImageSidebarCollapsed ? (
          <div
            className="absolute inset-y-0 left-0 z-[3] w-3 -translate-x-1/2 cursor-col-resize before:absolute before:inset-y-0 before:left-1/2 before:w-px before:-translate-x-1/2 before:bg-line-soft before:content-['']"
            onPointerDown={onBeginChatLatestImageSidebarResize}
          />
        ) : null}
        {chatLatestImageSidebarMounted ? (
          <div
            className={cx(
              "chat-sidebar-density h-full min-h-0 py-2",
              sidebarContentMotionClass,
              chatLatestImageSidebarWidth <= 200 && "chat-sidebar-narrow",
              chatLatestImageSidebarCollapsed ? "pointer-events-none translate-x-8 pl-0 pr-0 opacity-0" : "translate-x-0 pl-2 pr-2 opacity-100",
            )}
          >
            <div className="grid h-full min-h-0 grid-rows-[minmax(0,1fr)_auto] gap-2">
              <ChatRightSidebar
                canGoToNextImage={canGoToNextChatImage}
                canGoToPreviousImage={canGoToPreviousChatImage}
                currentMood={currentMood}
                imagePath={chatLatestImagePath}
                lonelinessValue={lonelinessValue}
                mode={sidebarMode}
                moodIllustrationUrl={moodIllustrationUrl}
                relationshipTags={relationshipTags}
                renderHeavyVisuals={renderHeavyVisuals}
                roleSelfView={roleSelfView}
                tasks={roleTasks.tasks}
                taskError={roleTasks.error}
                taskOperation={roleTasks.operation}
                onClearTaskError={roleTasks.clearError}
                onCreateTask={roleTasks.create}
                onUpdateTask={roleTasks.update}
                onCancelTask={roleTasks.cancel}
                onGoToNextImage={onGoToNextChatImage}
                onGoToPreviousImage={onGoToPreviousChatImage}
                onOpenImageLightbox={onOpenChatImageLightbox}
              />
              <ChatPanelSegments
                mode={sidebarMode}
                badges={panelBadges}
                statusAvailable={hasStatusContent}
                onSelect={setSidebarMode}
              />
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}
