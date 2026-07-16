import React, { useEffect, useEffectEvent, useLayoutEffect, useRef, useState } from "react";
import { ChatComposer } from "./ChatComposer";
import { ChatHeader } from "./ChatHeader";
import { ChatMessageContextMenu } from "./ChatMessageContextMenu";
import { ChatMessageList } from "./ChatMessageList";
import {
  getChatMessageCopyText,
  getChatMessageReplyContent,
  type MessageContextMenuState,
} from "./chatMessageActions";
import { ChatRightSidebar, type ChatSidebarMode } from "./ChatRightSidebar";
import {
  getExpandedVisibleChatMessageCountForKey,
  getVisibleChatMessages,
  initialVisibleChatMessageCount,
  visibleChatMessageCountStep,
} from "./chatMessageWindow";
import { shouldAutoScrollOnNewMessage } from "./chatAutoScroll";
import { summarizeChatReplyContent } from "./chatComposerState";
import { useRoleTasks } from "./useRoleTasks";
import { cx } from "../shared/styles";
import type { ChatReplyTarget, ChatSendRequest, RoleRecord, SessionMessage, SessionPayload } from "../shared/types";

type ChatSurfaceProps = {
  activeRole: RoleRecord | null;
  activeRoleId: string;
  activeSession: SessionPayload | null;
  bridgeReady: boolean;
  chatLatestImagePath: string;
  chatLatestImagePosition: number;
  chatLatestImageSidebarAnimating: boolean;
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
  notice: string;
  sending: boolean;
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
  onToggleChatLatestImageSidebar: () => void;
};

const emptySessionMessages: SessionMessage[] = [];

/** Renders the active role chat header, conversation messages, and composer. */
export function ChatSurface({
  activeRole,
  activeRoleId,
  activeSession,
  bridgeReady,
  chatLatestImagePath,
  chatLatestImagePosition,
  chatLatestImageSidebarAnimating,
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
  notice,
  sending,
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
  onToggleChatLatestImageSidebar,
}: ChatSurfaceProps) {
  const [visualsActive, setVisualsActive] = useState(() => (
    typeof document === "undefined" ? true : !document.hidden
  ));
  const conversationListRef = useRef<HTMLDivElement | null>(null);
  const messageContextMenuRef = useRef<HTMLDivElement | null>(null);
  const previousMessageCountRef = useRef(0);
  const previousLastMessageContentRef = useRef("");
  const previousChatImageCountRef = useRef(0);
  const previousRoleSelfViewRef = useRef(roleSelfView);
  const imagePriorityUserMessageCountRef = useRef(-1);
  const autoScrollingRef = useRef(false);
  const stickToBottomRef = useRef(true);
  const [scrollState, setScrollState] = useState({ isAtBottom: true, isScrollable: false });
  const [chatLatestImageSidebarMounted, setChatLatestImageSidebarMounted] = useState(!chatLatestImageSidebarCollapsed);
  const [messageContextMenu, setMessageContextMenu] = useState<MessageContextMenuState | null>(null);
  const [composerReplyTarget, setComposerReplyTarget] = useState<ChatReplyTarget | null>(null);
  const [visibleMessageCount, setVisibleMessageCount] = useState(initialVisibleChatMessageCount);
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
  const currentUserMessageCount = sessionMessages.reduce(
    (count, message) => count + (message.role === "user" ? 1 : 0),
    0,
  );
  const currentLastMessageContent = sessionMessages.at(-1)?.content ?? "";
  const sidebarToggleGlyphClass =
    "relative h-[11px] w-3 rounded-[4px] border-[1.2px] border-current before:absolute before:w-px before:rounded-full before:bg-current before:content-['']";

  const scrollConversationToBottom = useEffectEvent((behavior: ScrollBehavior): void => {
    autoScrollingRef.current = true;
    stickToBottomRef.current = true;
    conversationEndRef.current?.scrollIntoView({ behavior, block: "end" });
    window.setTimeout(() => {
      autoScrollingRef.current = false;
    }, behavior === "smooth" ? 320 : 0);
  });

  const resetConversationForSession = useEffectEvent(() => {
    previousMessageCountRef.current = activeSession?.messages.length ?? 0;
    previousLastMessageContentRef.current = activeSession?.messages.at(-1)?.content ?? "";
    previousChatImageCountRef.current = chatLatestImageSidebarCount;
    previousRoleSelfViewRef.current = roleSelfView;
    imagePriorityUserMessageCountRef.current = -1;
    const container = conversationListRef.current;
    if (!container) return;
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
    const updateScrollState = (options?: { allowUnstick?: boolean }) => {
      const container = conversationListRef.current;
      if (!container) return;

      const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
      const nextState = {
        isAtBottom: distanceFromBottom <= 24,
        isScrollable: container.scrollHeight - container.clientHeight > 24,
      };

      if (nextState.isAtBottom) {
        stickToBottomRef.current = true;
      } else if (options?.allowUnstick && !autoScrollingRef.current) {
        stickToBottomRef.current = false;
      }

      setScrollState((current) => (
        current.isAtBottom === nextState.isAtBottom && current.isScrollable === nextState.isScrollable
          ? current
          : nextState
      ));
    };

    updateScrollState();

    const container = conversationListRef.current;
    if (!container) return;

    const handleScroll = () => updateScrollState({ allowUnstick: true });
    const handleResize = () => updateScrollState();

    container.addEventListener("scroll", handleScroll, { passive: true });
    window.addEventListener("resize", handleResize);

    const resizeObserver = new ResizeObserver(() => updateScrollState());
    resizeObserver.observe(container);

    return () => {
      container.removeEventListener("scroll", handleScroll);
      window.removeEventListener("resize", handleResize);
      resizeObserver.disconnect();
    };
  }, [activeSession?.messages.length, currentLastMessageContent, highlightedMessageKey, sending]);

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

  useEffect(() => {
    if (!messageContextMenu) return undefined;

    const closeContextMenu = () => setMessageContextMenu(null);
    const handlePointerDown = (event: PointerEvent) => {
      const menu = messageContextMenuRef.current;
      if (menu && event.target instanceof Node && menu.contains(event.target)) {
        return;
      }
      closeContextMenu();
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        closeContextMenu();
      }
    };

    window.addEventListener("pointerdown", handlePointerDown, true);
    window.addEventListener("scroll", closeContextMenu, true);
    window.addEventListener("resize", closeContextMenu);
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("pointerdown", handlePointerDown, true);
      window.removeEventListener("scroll", closeContextMenu, true);
      window.removeEventListener("resize", closeContextMenu);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [messageContextMenu]);

  useEffect(() => {
    resetConversationForSession();
  }, [activeSession?.key]);

  useEffect(() => {
    const previousImageCount = previousChatImageCountRef.current;
    const previousRoleSelfView = previousRoleSelfViewRef.current;
    previousChatImageCountRef.current = chatLatestImageSidebarCount;
    previousRoleSelfViewRef.current = roleSelfView;
    const hasNewImage = chatLatestImageSidebarCount > previousImageCount;
    const hasUpdatedSelfView = Boolean(roleSelfView) && roleSelfView !== previousRoleSelfView;
    if (!hasNewImage && !hasUpdatedSelfView) {
      return;
    }
    if (hasNewImage) {
      imagePriorityUserMessageCountRef.current = currentUserMessageCount;
      setSidebarMode("images");
    } else if (imagePriorityUserMessageCountRef.current !== currentUserMessageCount) {
      setSidebarMode("status");
    } else {
      return;
    }
    if (chatLatestImageSidebarCollapsed) {
      onToggleChatLatestImageSidebar();
    }
  }, [
    chatLatestImageSidebarCollapsed,
    chatLatestImageSidebarCount,
    currentUserMessageCount,
    onToggleChatLatestImageSidebar,
    roleSelfView,
  ]);

  useEffect(() => {
    setComposerReplyTarget(null);
  }, [activeRoleId, activeSession?.key]);

  useEffect(() => {
    setVisibleMessageCount(initialVisibleChatMessageCount);
  }, [activeSession?.key]);

  const visibleMessageWindow = getVisibleChatMessages(sessionMessages, visibleMessageCount);

  useLayoutEffect(() => {
    const nextVisibleMessageCount = getExpandedVisibleChatMessageCountForKey(
      sessionMessages,
      visibleMessageCount,
      highlightedMessageKey,
    );
    if (nextVisibleMessageCount !== visibleMessageCount) {
      setVisibleMessageCount(nextVisibleMessageCount);
    }
  }, [highlightedMessageKey, sessionMessages, visibleMessageCount]);

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
  }, [activeSession?.messages.length, currentLastMessageContent, conversationEndRef, highlightedMessageKey, sending]);

  const renderHeavyVisuals = visualsActive && windowVisible;
  const hasIllustration = Boolean(visibleIllustrationUrl) && renderHeavyVisuals;
  const showScrollToBottom = scrollState.isScrollable && !scrollState.isAtBottom;
  const hasChatImageHistory = chatLatestImageSidebarCount > 0;
  const canGoToPreviousChatImage = chatLatestImagePosition > 1;
  const canGoToNextChatImage = hasChatImageHistory && chatLatestImagePosition < chatLatestImageSidebarCount;
  const canOpenRoleDetail = Boolean(activeRole && activeRoleId);
  const detailRole = canOpenRoleDetail ? activeRole : null;

  const handleScrollToBottom = () => {
    const container = conversationListRef.current;
    if (!container) return;
    container.scrollTo({ top: container.scrollHeight, behavior: "smooth" });
    autoScrollingRef.current = true;
    stickToBottomRef.current = true;
    window.setTimeout(() => {
      autoScrollingRef.current = false;
    }, 320);
  };

  const handleOpenChatImagePreview = (historyKey: string) => {
    setSidebarMode("images");
    onOpenChatImagePreview({ historyKey });
  };

  const handleOpenRoleDetail = () => {
    if (!canOpenRoleDetail) return;
    onOpenRoleDetail();
  };

  function openMessageContextMenu(
    event: React.MouseEvent<HTMLElement>,
    message: SessionMessage,
    messageKey: string,
    sender: string,
  ): void {
    event.preventDefault();
    event.stopPropagation();
    setMessageContextMenu({
      x: Math.min(event.clientX, Math.max(12, window.innerWidth - 148)),
      y: Math.min(event.clientY, Math.max(12, window.innerHeight - 84)),
      message,
      messageKey,
      sender,
    });
  }

  function copyContextMessage(): void {
    if (!messageContextMenu) return;
    onCopyMessage(getChatMessageCopyText(messageContextMenu.message));
    setMessageContextMenu(null);
  }

  function quoteContextMessage(): void {
    if (!messageContextMenu) return;
    const content = getChatMessageReplyContent(messageContextMenu.message);
    if (!content) return;
    setComposerReplyTarget({
      messageId: messageContextMenu.messageKey,
      content,
      sender: messageContextMenu.sender,
      preview: summarizeChatReplyContent(content),
    });
    setMessageContextMenu(null);
  }

  return (
    <section className="chat-surface relative grid h-full min-h-0 grid-cols-[minmax(0,1fr)_auto] overflow-hidden bg-[var(--chat-bg)]">
      <button
        className="absolute right-4 top-4 z-[5] m-0 grid h-6 w-6 place-items-center rounded-md border-0 bg-transparent p-0 text-[#747474] transition hover:bg-black/5 hover:text-[#4B4B4B] focus:outline-none"
        type="button"
        aria-label={chatLatestImageSidebarCollapsed ? "展开最新图片侧栏" : "收起最新图片侧栏"}
        aria-expanded={!chatLatestImageSidebarCollapsed}
        onClick={onToggleChatLatestImageSidebar}
      >
        <span
          className={cx(
            sidebarToggleGlyphClass,
            chatLatestImageSidebarCollapsed
              ? "before:bottom-[2.2px] before:right-[0.8px] before:top-[2.2px]"
              : "before:bottom-0 before:right-[3.3px] before:top-0",
          )}
        />
      </button>
      {messageContextMenu ? (
        <ChatMessageContextMenu
          menu={messageContextMenu}
          menuRef={messageContextMenuRef}
          sending={sending}
          onCopy={copyContextMessage}
          onQuote={quoteContextMessage}
        />
      ) : null}
      <div className="relative grid h-full min-h-0 grid-rows-chat overflow-hidden">
      {hasIllustration ? (
        <div
          className="conversation-illustration pointer-events-none absolute inset-0 z-0 overflow-hidden"
          aria-hidden="true"
        >
          <div
            className="conversation-illustration-image absolute inset-0 bg-cover bg-center bg-no-repeat opacity-[0.96]"
            style={{ backgroundImage: `url("${visibleIllustrationUrl}")` }}
          />
          <div className="conversation-illustration-fade absolute inset-0 bg-[linear-gradient(90deg,rgba(255,255,255,0.78)_0%,rgba(255,255,255,0.64)_24%,rgba(255,255,255,0.4)_48%,rgba(255,255,255,0.14)_72%,rgba(255,255,255,0.03)_100%)]" />
        </div>
      ) : null}
      <ChatHeader
        activeRole={activeRole}
        detailRole={detailRole}
        title={headerTitle}
        onOpenRoleDetail={handleOpenRoleDetail}
      />
      <section className="conversation-panel relative z-[1] h-full min-h-0 overflow-hidden bg-transparent">
        {notice ? <div className="notice-chip absolute left-1/2 top-4 z-[2] -translate-x-1/2 rounded-[14px] border border-[rgba(26,106,58,0.18)] bg-[#edf8f0] px-3.5 py-2.5 text-[#1a6a3a]">{notice}</div> : null}
        <ChatMessageList
          activeRole={activeRole}
          conversationEndRef={conversationEndRef}
          conversationListRef={conversationListRef}
          highlightedMessageKey={highlightedMessageKey}
          visibleMessageWindow={visibleMessageWindow}
          onBeginAttachmentDrag={onBeginAttachmentDrag}
          onExpandOlderMessages={() => (
            setVisibleMessageCount((current) => current + visibleChatMessageCountStep)
          )}
          onJumpToMessage={onJumpToMessage}
          onOpenContextMenu={openMessageContextMenu}
          onOpenImagePreview={handleOpenChatImagePreview}
        />
        {showScrollToBottom ? (
          <div className="pointer-events-none absolute inset-x-0 bottom-[132px] z-[2] flex justify-center">
            <button
              className="pointer-events-auto grid h-9 w-9 place-items-center rounded-full border border-[#E4E4E4] bg-[rgba(255,255,255,0.96)] text-[#4b5563] shadow-[0_10px_24px_rgba(17,24,39,0.08)] transition hover:border-[#d5d5d5] hover:bg-white hover:text-[#1f2937] focus:outline-none"
              type="button"
              aria-label="滑到最下方"
              onClick={handleScrollToBottom}
            >
              <svg className="h-[16px] w-[16px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M12 5v14" />
                <path d="m6 13 6 6 6-6" />
              </svg>
            </button>
          </div>
        ) : null}
        <ChatComposer
          activeRoleId={activeRoleId}
          sessionKey={activeSession?.key ?? ""}
          bridgeReady={bridgeReady}
          sending={sending}
          replyTarget={composerReplyTarget}
          onSendMessage={onSendMessage}
          onClearReplyTarget={() => setComposerReplyTarget(null)}
          onJumpToMessage={onJumpToMessage}
        />
      </section>
      </div>
      <div
        className={cx(
          "relative h-full overflow-hidden border-l border-[#E0E6EE] bg-[rgba(244,247,251,0.92)]",
          chatLatestImageSidebarAnimating && "transition-[width] duration-[480ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
        )}
        style={{ width: chatLatestImageSidebarCollapsed ? 0 : chatLatestImageSidebarWidth }}
      >
        {!chatLatestImageSidebarCollapsed ? (
          <div
            className="absolute inset-y-0 left-0 z-[3] w-3 -translate-x-1/2 cursor-col-resize before:absolute before:inset-y-0 before:left-1/2 before:w-px before:-translate-x-1/2 before:bg-[#D8DEE8] before:content-['']"
            onPointerDown={onBeginChatLatestImageSidebarResize}
          />
        ) : null}
        {chatLatestImageSidebarMounted ? (
          <div
            className={cx(
              "h-full min-h-0 pb-3 pt-3 transition-[opacity,transform] duration-200",
              chatLatestImageSidebarCollapsed ? "pointer-events-none translate-x-8 pl-0 pr-0 opacity-0" : "translate-x-0 pl-2 pr-2 opacity-100",
            )}
          >
            <div className="grid h-full min-h-0 grid-rows-[minmax(0,1fr)_auto] gap-3">
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
              <div className="justify-self-center inline-flex w-fit rounded-full border border-[#D8DFE7] bg-[#F6F8FB] p-1">
                <button
                  className={cx(
                    "grid h-7 w-7 place-items-center rounded-full text-sm transition",
                    sidebarMode === "status" ? "bg-[#272536] text-white shadow-[0_6px_16px_rgba(39,37,54,0.18)]" : "text-[#5B6472] hover:text-[#272536]",
                    !hasStatusContent && "cursor-default opacity-45 hover:text-[#5B6472]",
                  )}
                  type="button"
                  aria-label="状态侧栏"
                  disabled={!hasStatusContent}
                  onClick={() => setSidebarMode("status")}
                >
                  <svg viewBox="0 0 1024 1024" className="h-[14px] w-[14px] fill-current" aria-hidden="true">
                    <path d="M512 133.567c51.136 0 100.66 10.053 147.327 29.664 45.055 19.114 85.517 46.42 120.27 81.172 34.753 34.753 62.058 75.215 81.172 120.27 19.735 46.668 29.664 96.19 29.664 147.327S880.38 612.66 860.77 659.327c-19.114 45.055-46.42 85.517-81.172 120.27-34.753 34.753-75.215 62.058-120.27 81.172-46.668 19.735-96.19 29.664-147.327 29.664S411.34 880.38 364.673 860.77c-45.055-19.114-85.517-46.42-120.27-81.172-34.753-34.753-62.058-75.215-81.172-120.27-19.735-46.668-29.664-96.19-29.664-147.327s10.053-100.66 29.664-147.327c19.114-45.055 46.42-85.517 81.172-120.27 34.753-34.753 75.215-62.058 120.27-81.172 46.668-19.735 96.19-29.664 147.327-29.664m0-65.783C266.62 67.784 67.784 266.62 67.784 512S266.62 956.216 512 956.216 956.216 757.38 956.216 512 757.38 67.784 512 67.784zM346.8 349.903c-26.065 0-47.165 21.1-47.165 47.164s21.1 47.165 47.165 47.165 47.165-21.1 47.165-47.165-21.1-47.164-47.165-47.164z m330.4 0c-26.065 0-47.165 21.1-47.165 47.164s21.1 47.165 47.165 47.165 47.165-21.1 47.165-47.165-21.1-47.164-47.165-47.164z m11.791 288.448c8.192-15.018 2.483-33.884-12.536-42.075-15.018-8.192-33.884-2.483-42.075 12.535-24.327 45.055-71.368 73.106-122.504 73.106-51.012 0-97.929-27.927-122.38-72.857-8.191-15.019-27.057-20.604-42.075-12.412-15.019 8.192-20.604 27.058-12.412 42.076 35.25 64.913 103.017 105.251 176.867 105.251 74.098 0 141.866-40.462 177.115-105.624z" />
                  </svg>
                </button>
                <button
                  className={cx("grid h-7 w-7 place-items-center rounded-full text-sm transition", sidebarMode === "tasks" ? "bg-[#272536] text-white shadow-[0_6px_16px_rgba(39,37,54,0.18)]" : "text-[#5B6472] hover:text-[#272536]")}
                  type="button"
                  aria-label="任务侧栏"
                  onClick={() => setSidebarMode("tasks")}
                >
                  <svg viewBox="0 0 1024 1024" className="h-[14px] w-[14px] fill-current" aria-hidden="true"><path d="M884.8 1014.4H144c-36.8 0-67.2-30.4-67.2-67.2V209.6c0-36.8 30.4-67.2 67.2-67.2h33.6v100.8c0 36.8 30.4 67.2 67.2 67.2h538.4c36.8 0 67.2-30.4 67.2-67.2V142.4H884c36.8 0 67.2 30.4 67.2 67.2v737.6c.8 36.8-29.6 67.2-66.4 67.2z m-150.4-456c-20-19.2-52-19.2-72 0l-180 171.2-84-80c-20-19.2-52-19.2-72 0s-20 49.6 0 68l120 113.6c20 19.2 52 19.2 72 0l216-204.8c20-18.4 20-48.8 0-68z" /></svg>
                </button>
                <button
                  className={cx(
                    "grid h-7 w-7 place-items-center rounded-full text-sm transition",
                    sidebarMode === "images" ? "bg-[#272536] text-white shadow-[0_6px_16px_rgba(39,37,54,0.18)]" : "text-[#5B6472] hover:text-[#272536]",
                  )}
                  type="button"
                  aria-label="图片侧栏"
                  onClick={() => setSidebarMode("images")}
                >
                  <svg viewBox="0 0 1024 1024" className="h-[14px] w-[14px] fill-current" aria-hidden="true">
                    <path d="M356.774 578.668C279.812 528.088 229 440.978 229 342c0-156.297 126.703-283 283-283s283 126.703 283 283c0 98.978-50.812 186.088-127.774 236.668C808.213 638.98 907 778.953 907 942c0 24.3-19.7 44-44 44s-44-19.7-44-44c0-169.551-137.449-307-307-307S205 772.449 205 942c0 24.3-19.7 44-44 44s-44-19.7-44-44c0-163.047 98.787-303.02 239.774-363.332zM512 537c107.696 0 195-87.304 195-195s-87.304-195-195-195-195 87.304-195 195 87.304 195 195 195z" />
                  </svg>
                </button>
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}
