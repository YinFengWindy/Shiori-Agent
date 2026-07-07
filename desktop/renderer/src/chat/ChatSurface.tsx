import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { ChatComposer } from "./ChatComposer";
import { buildChatImageHistoryKey } from "./chatImageHistory";
import { isChatImageAsset } from "./chatImageHistory";
import { getChatMessageDomKey, getChatMessageReactKey } from "./chatMessageIdentity";
import {
  getExpandedVisibleChatMessageCountForKey,
  getVisibleChatMessages,
  initialVisibleChatMessageCount,
  visibleChatMessageCountStep,
} from "./chatMessageWindow";
import { shouldAutoScrollOnNewMessage } from "./chatAutoScroll";
import { summarizeChatReplyContent } from "./chatComposerState";
import { ChatStatusSidebar } from "./ChatStatusSidebar";
import { formatTimestamp, toFileUrl } from "../shared/format";
import { CopyIcon, DocumentIcon, QuoteIcon } from "../shared/icons";
import { cx } from "../shared/styles";
import type { ChatReplyTarget, ChatSendRequest, RoleRecord, SessionMessage, SessionPayload } from "../shared/types";

type MessageContextMenuState = {
  x: number;
  y: number;
  message: SessionMessage;
  messageKey: string;
  sender: string;
};

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
  moodIllustrationBindingHit: boolean;
  moodIllustrationUrl: string;
  hasMoodIllustrationBinding: boolean;
  roleSelfView: string;
  relationshipTags: string[];
  lonelinessValue: number;
  conversationEndRef: React.RefObject<HTMLDivElement | null>;
  headerTitle: string;
  highlightedMessageKey: string;
  notice: string;
  sending: boolean;
  visibleIllustrationUrl: string;
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
  moodIllustrationBindingHit,
  moodIllustrationUrl,
  hasMoodIllustrationBinding,
  roleSelfView,
  relationshipTags,
  lonelinessValue,
  conversationEndRef,
  headerTitle,
  highlightedMessageKey,
  notice,
  sending,
  visibleIllustrationUrl,
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
  const conversationListRef = useRef<HTMLDivElement | null>(null);
  const messageContextMenuRef = useRef<HTMLDivElement | null>(null);
  const previousMessageCountRef = useRef(0);
  const previousLastMessageContentRef = useRef("");
  const autoScrollingRef = useRef(false);
  const stickToBottomRef = useRef(true);
  const [scrollState, setScrollState] = useState({ isAtBottom: true, isScrollable: false });
  const [chatLatestImageSidebarMounted, setChatLatestImageSidebarMounted] = useState(!chatLatestImageSidebarCollapsed);
  const [messageContextMenu, setMessageContextMenu] = useState<MessageContextMenuState | null>(null);
  const [composerReplyTarget, setComposerReplyTarget] = useState<ChatReplyTarget | null>(null);
  const [visibleMessageCount, setVisibleMessageCount] = useState(initialVisibleChatMessageCount);
  const hasStatusIllustration = Boolean(moodIllustrationUrl);
  const [sidebarMode, setSidebarMode] = useState<"status" | "images">(
    hasStatusIllustration ? "status" : "images",
  );
  const sessionMessages = activeSession?.messages ?? [];
  const currentLastMessageContent = sessionMessages.at(-1)?.content ?? "";
  const sidebarToggleGlyphClass =
    "relative h-[11px] w-3 rounded-[4px] border-[1.2px] border-current before:absolute before:w-px before:rounded-full before:bg-current before:content-['']";

  const scrollConversationToBottom = (behavior: ScrollBehavior): void => {
    autoScrollingRef.current = true;
    stickToBottomRef.current = true;
    conversationEndRef.current?.scrollIntoView({ behavior, block: "end" });
    window.setTimeout(() => {
      autoScrollingRef.current = false;
    }, behavior === "smooth" ? 320 : 0);
  };

  useEffect(() => {
    const updateScrollState = () => {
      const container = conversationListRef.current;
      if (!container) return;

      const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
      const nextState = {
        isAtBottom: distanceFromBottom <= 24,
        isScrollable: container.scrollHeight - container.clientHeight > 24,
      };

      if (nextState.isAtBottom) {
        stickToBottomRef.current = true;
      } else if (!autoScrollingRef.current) {
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

    container.addEventListener("scroll", updateScrollState, { passive: true });
    window.addEventListener("resize", updateScrollState);

    const resizeObserver = new ResizeObserver(() => updateScrollState());
    resizeObserver.observe(container);

    return () => {
      container.removeEventListener("scroll", updateScrollState);
      window.removeEventListener("resize", updateScrollState);
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
    if (hasStatusIllustration || sidebarMode !== "status") {
      return;
    }
    setSidebarMode("images");
  }, [hasStatusIllustration, sidebarMode]);

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
    previousMessageCountRef.current = activeSession?.messages.length ?? 0;
    previousLastMessageContentRef.current = activeSession?.messages.at(-1)?.content ?? "";
    const container = conversationListRef.current;
    if (!container) return;
    stickToBottomRef.current = true;
    scrollConversationToBottom("auto");
  }, [activeSession?.key]);

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

  const headerAvatarClass =
    "chat-header-avatar grid h-[34px] w-[34px] flex-none place-items-center rounded-full border border-black/10 object-cover";
  const agentAvatarClass =
    "message-avatar grid h-8 w-8 flex-none place-items-center overflow-hidden rounded-full border border-black/10 bg-[#f6f6f6] object-cover";
  const chatBodyClass = "text-sm leading-6";
  const chatMinorTextClass = "text-[12px]";
  const chatContentTrackClass = "mx-auto w-full max-w-[860px] px-5 md:px-6";
  const composerTrackClass = "mx-auto w-full max-w-[700px] px-5 md:px-6";
  const sidebarNavButtonClass =
    "pointer-events-auto grid h-9 w-9 place-items-center rounded-full border border-transparent bg-transparent text-[#4B5563] transition hover:border-black hover:bg-white/92 hover:text-[#1F2937] focus:outline-none disabled:cursor-default disabled:opacity-40";
  const assistantMessageBubbleClass =
    "message-bubble w-fit max-w-full rounded-[14px] border border-[rgba(228,228,228,0.66)] bg-[rgba(255,255,255,0.48)] px-3.5 py-2.5 text-left shadow-[0_1px_2px_rgba(0,0,0,0.03)] backdrop-blur-[10px] transition-colors duration-150 group-hover:bg-[rgba(255,255,255,0.72)]";
  const userMessageBubbleClass =
    "message-bubble w-fit max-w-full rounded-[14px] border border-[#E4E4E4] bg-white px-3.5 py-2.5 text-left shadow-[0_1px_2px_rgba(0,0,0,0.04)]";
  const hasIllustration = Boolean(visibleIllustrationUrl);
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

  const handleOpenRoleDetail = () => {
    if (!canOpenRoleDetail) return;
    onOpenRoleDetail();
  };

  function getAttachmentName(path: string): string {
    return path.split(/[\\/]/).pop() || path;
  }

  function getMessageSourceLabel(message: SessionPayload["messages"][number]): string | null {
    const metadata = message.metadata ?? {};
    const transportChannel = String(metadata.transport_channel ?? metadata.context_channel ?? metadata.source_channel ?? "").trim();
    if (transportChannel) {
      return transportChannel.toUpperCase();
    }
    if (String(metadata.source ?? "").trim() === "desktop") {
      return "DESKTOP";
    }
    return null;
  }

  function getMessageCopyText(message: SessionMessage): string {
    return message.content.trim();
  }

  function getMessageReplyContent(message: SessionMessage): string {
    const content = message.content.trim();
    if (content) return content;
    const media = Array.isArray(message.media) ? message.media.filter((item) => item.trim()) : [];
    if (!media.length) return "";
    return media.some((item) => isChatImageAsset(item)) ? "[图片]" : "[附件]";
  }

  function getStoredReplyPreview(message: SessionMessage): ChatReplyTarget | null {
    const metadata = message.metadata ?? {};
    const replyContent = String(metadata.reply_to_content ?? "").trim();
    if (!replyContent) return null;
    const messageId = String(metadata.reply_to_message_id ?? "").trim();
    const sender = String(metadata.reply_to_sender ?? "").trim();
    return {
      messageId,
      content: replyContent,
      sender,
      preview: summarizeChatReplyContent(replyContent),
    };
  }

  function handleAttachmentDragStart(event: React.DragEvent<HTMLElement>, path: string): void {
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.effectAllowed = "copy";
    onBeginAttachmentDrag(path);
  }

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
    onCopyMessage(getMessageCopyText(messageContextMenu.message));
    setMessageContextMenu(null);
  }

  function quoteContextMessage(): void {
    if (!messageContextMenu) return;
    const content = getMessageReplyContent(messageContextMenu.message);
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
        <div
          ref={messageContextMenuRef}
          data-testid="message-context-menu"
          className="fixed z-50 min-w-[132px] overflow-hidden rounded-md border border-[#E4E7EC] bg-white py-1 text-sm text-[#1F2937] shadow-[0_16px_40px_rgba(15,23,42,0.16)]"
          style={{ left: messageContextMenu.x, top: messageContextMenu.y }}
          role="menu"
          onClick={(event) => event.stopPropagation()}
          onContextMenu={(event) => {
            event.preventDefault();
            event.stopPropagation();
          }}
        >
          <button
            data-testid="message-context-menu-copy"
            className="flex h-8 w-full items-center gap-2 px-3 text-left transition hover:bg-[#F5F7FA] focus:bg-[#F5F7FA] focus:outline-none disabled:cursor-default disabled:opacity-45"
            type="button"
            role="menuitem"
            onClick={copyContextMessage}
            disabled={!getMessageCopyText(messageContextMenu.message)}
          >
            <CopyIcon className="h-[14px] w-[14px] fill-current" />
            <span>复制</span>
          </button>
          <button
            data-testid="message-context-menu-quote"
            className="flex h-8 w-full items-center gap-2 px-3 text-left transition hover:bg-[#F5F7FA] focus:bg-[#F5F7FA] focus:outline-none disabled:cursor-default disabled:opacity-45"
            type="button"
            role="menuitem"
            onClick={quoteContextMessage}
            disabled={!getMessageReplyContent(messageContextMenu.message) || sending}
          >
            <QuoteIcon className="h-[14px] w-[14px] fill-current" />
            <span>引用</span>
          </button>
        </div>
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
      <header className="chat-header relative z-[1] flex min-w-0 items-center gap-3 border-b border-[#E4E4E4] bg-[rgba(255,255,255,0.55)] pl-[23px] pr-6 backdrop-blur-[3px]" data-testid="session-hero">
        {detailRole ? (
          <button
            className="rounded-full transition hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-primary/20"
            type="button"
            aria-label={`查看角色 ${detailRole.name} 详情`}
            data-testid="chat-header-avatar-button"
            onClick={handleOpenRoleDetail}
          >
            {detailRole.avatar_abs ? (
              <img
                className={headerAvatarClass}
                src={toFileUrl(detailRole.avatar_abs)}
                alt={`${detailRole.name} avatar`}
              />
            ) : (
              <span className={cx(headerAvatarClass, "chat-header-avatar-fallback bg-[#f6f6f6] text-sm font-bold text-[#333333]")}>
                {detailRole.name.slice(0, 1).toUpperCase()}
              </span>
            )}
          </button>
        ) : activeRole?.avatar_abs ? (
          <img
            className={headerAvatarClass}
            src={toFileUrl(activeRole.avatar_abs)}
            alt={`${activeRole.name} avatar`}
          />
        ) : (
          <span className={cx(headerAvatarClass, "chat-header-avatar-fallback bg-[#f6f6f6] text-sm font-bold text-[#333333]")}>
            {activeRole ? activeRole.name.slice(0, 1).toUpperCase() : "M"}
          </span>
        )}
        <div className="chat-header-title min-w-0 flex-1 truncate text-sm font-semibold text-[#1f1f1f]">{headerTitle}</div>
      </header>
      <section className="conversation-panel relative z-[1] h-full min-h-0 overflow-hidden bg-transparent">
        {notice ? <div className="notice-chip absolute left-1/2 top-4 z-[2] -translate-x-1/2 rounded-[14px] border border-[rgba(26,106,58,0.18)] bg-[#edf8f0] px-3.5 py-2.5 text-[#1a6a3a]">{notice}</div> : null}
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
                  className="rounded-md border border-[#D8DEE8] bg-white/85 px-3 py-1.5 text-[12px] text-[#5B6472] transition hover:border-[#C6CEDA] hover:bg-white focus:outline-none focus:ring-2 focus:ring-primary/20"
                  type="button"
                  onClick={() => setVisibleMessageCount((current) => current + visibleChatMessageCountStep)}
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
              const sourceLabel = getMessageSourceLabel(message);
              const media = Array.isArray(message.media) ? message.media : [];
              const storedReplyPreview = getStoredReplyPreview(message);
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
                  onContextMenu={(event) => openMessageContextMenu(event, message, messageDomKey, authorLabel)}
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
                      <div className={cx(bubbleClass, isHighlighted && "message-bubble-highlight ring-2 ring-[#111827]/10")}>
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
                        {media.length ? (
                          <div className="mt-3 grid gap-2">
                            {media.map((item, mediaIndex) => (
                              isChatImageAsset(item) ? (
                                <button
                                  key={`${messageDomKey}:${mediaIndex}:${item}`}
                                  className="block cursor-grab overflow-hidden rounded-[12px] border border-black/8 bg-white/70 p-0 text-left transition hover:bg-white active:cursor-grabbing focus:outline-none"
                                  type="button"
                                  draggable
                                  onDragStart={(event) => handleAttachmentDragStart(event, item)}
                                  onClick={() => onOpenChatImagePreview({ historyKey: buildChatImageHistoryKey(messageDomKey, mediaIndex) })}
                                >
                                  <img className="max-h-[280px] w-full object-cover" src={toFileUrl(item)} alt="message attachment" />
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
                                  <span className="truncate font-medium">{getAttachmentName(item)}</span>
                                </a>
                              )
                            ))}
                          </div>
                        ) : null}
                      </div>
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
              {sidebarMode === "status" ? (
                <ChatStatusSidebar
                  currentMood={currentMood}
                  moodIllustrationUrl={moodIllustrationUrl}
                  roleSelfView={roleSelfView}
                  relationshipTags={relationshipTags}
                  lonelinessValue={lonelinessValue}
                />
              ) : (
                <div className="grid h-full min-h-0 rounded-[20px] bg-[#FBFCFE] p-3 shadow-[0_8px_24px_rgba(15,23,42,0.05)]">
                  <div className="relative grid h-full min-h-0 place-items-center overflow-hidden rounded-[16px] bg-[#F1F5F9]">
                    <div className="pointer-events-none absolute inset-y-0 left-0 z-[2] flex items-center pl-3">
                      <button
                        className={sidebarNavButtonClass}
                        type="button"
                        aria-label="查看上一张聊天图片"
                        onClick={onGoToPreviousChatImage}
                        disabled={!canGoToPreviousChatImage}
                      >
                        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                          <path d="m15 18-6-6 6-6" />
                        </svg>
                      </button>
                    </div>
                    {chatLatestImagePath ? (
                      <button
                        className="grid h-full w-full place-items-center border-0 bg-transparent p-0"
                        type="button"
                        aria-label="放大查看当前聊天图片"
                        onClick={onOpenChatImageLightbox}
                      >
                        <img
                          className="max-h-full max-w-full object-contain"
                          src={toFileUrl(chatLatestImagePath)}
                          alt="selected message image"
                        />
                      </button>
                    ) : (
                      <div className="grid gap-2 px-6 text-center">
                        <div className="mx-auto h-10 w-10 rounded-[14px] border border-[#D6DCE5] bg-white/70" />
                        <div className="text-[12px] text-[#6B7280]">当前聊天里出现的图片会显示在这里</div>
                      </div>
                    )}
                    <div className="pointer-events-none absolute inset-y-0 right-0 z-[2] flex items-center pr-3">
                      <button
                        className={sidebarNavButtonClass}
                        type="button"
                        aria-label="查看下一张聊天图片"
                        onClick={onGoToNextChatImage}
                        disabled={!canGoToNextChatImage}
                      >
                        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                          <path d="m9 18 6-6-6-6" />
                        </svg>
                      </button>
                    </div>
                  </div>
                </div>
              )}
              <div className="justify-self-center inline-flex w-fit rounded-full border border-[#D8DFE7] bg-[#F6F8FB] p-1">
                <button
                  className={cx(
                    "grid h-7 w-7 place-items-center rounded-full text-sm transition",
                    sidebarMode === "status" ? "bg-[#272536] text-white shadow-[0_6px_16px_rgba(39,37,54,0.18)]" : "text-[#5B6472] hover:text-[#272536]",
                    !hasStatusIllustration && "cursor-default opacity-45 hover:text-[#5B6472]",
                  )}
                  type="button"
                  aria-label="状态侧栏"
                  disabled={!hasStatusIllustration}
                  onClick={() => setSidebarMode("status")}
                >
                  <svg viewBox="0 0 1024 1024" className="h-[14px] w-[14px] fill-current" aria-hidden="true">
                    <path d="M512 133.567c51.136 0 100.66 10.053 147.327 29.664 45.055 19.114 85.517 46.42 120.27 81.172 34.753 34.753 62.058 75.215 81.172 120.27 19.735 46.668 29.664 96.19 29.664 147.327S880.38 612.66 860.77 659.327c-19.114 45.055-46.42 85.517-81.172 120.27-34.753 34.753-75.215 62.058-120.27 81.172-46.668 19.735-96.19 29.664-147.327 29.664S411.34 880.38 364.673 860.77c-45.055-19.114-85.517-46.42-120.27-81.172-34.753-34.753-62.058-75.215-81.172-120.27-19.735-46.668-29.664-96.19-29.664-147.327s10.053-100.66 29.664-147.327c19.114-45.055 46.42-85.517 81.172-120.27 34.753-34.753 75.215-62.058 120.27-81.172 46.668-19.735 96.19-29.664 147.327-29.664m0-65.783C266.62 67.784 67.784 266.62 67.784 512S266.62 956.216 512 956.216 956.216 757.38 956.216 512 757.38 67.784 512 67.784zM346.8 349.903c-26.065 0-47.165 21.1-47.165 47.164s21.1 47.165 47.165 47.165 47.165-21.1 47.165-47.165-21.1-47.164-47.165-47.164z m330.4 0c-26.065 0-47.165 21.1-47.165 47.164s21.1 47.165 47.165 47.165 47.165-21.1 47.165-47.165-21.1-47.164-47.165-47.164z m11.791 288.448c8.192-15.018 2.483-33.884-12.536-42.075-15.018-8.192-33.884-2.483-42.075 12.535-24.327 45.055-71.368 73.106-122.504 73.106-51.012 0-97.929-27.927-122.38-72.857-8.191-15.019-27.057-20.604-42.075-12.412-15.019 8.192-20.604 27.058-12.412 42.076 35.25 64.913 103.017 105.251 176.867 105.251 74.098 0 141.866-40.462 177.115-105.624z" />
                  </svg>
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
