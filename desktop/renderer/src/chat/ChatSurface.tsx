import type React from "react";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { isChatImageAsset } from "./chatImageHistory";
import { formatTimestamp, toFileUrl } from "../shared/format";
import { cx } from "../shared/styles";
import type { RoleRecord, SessionPayload } from "../shared/types";

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
  conversationEndRef: React.RefObject<HTMLDivElement | null>;
  draft: string;
  headerTitle: string;
  highlightedMessageKey: string;
  notice: string;
  sending: boolean;
  visibleIllustrationUrl: string;
  onBeginChatLatestImageSidebarResize: (event: React.PointerEvent<HTMLDivElement>) => void;
  onGoToNextChatImage: () => void;
  onGoToPreviousChatImage: () => void;
  onOpenChatImagePreview: (path: string) => void;
  onSendMessage: (contentOverride?: string) => void;
  onToggleChatLatestImageSidebar: () => void;
  onUpdateDraft: (value: string) => void;
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
  conversationEndRef,
  draft,
  headerTitle,
  highlightedMessageKey,
  notice,
  sending,
  visibleIllustrationUrl,
  onBeginChatLatestImageSidebarResize,
  onGoToNextChatImage,
  onGoToPreviousChatImage,
  onOpenChatImagePreview,
  onSendMessage,
  onToggleChatLatestImageSidebar,
  onUpdateDraft,
}: ChatSurfaceProps) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const conversationListRef = useRef<HTMLDivElement | null>(null);
  const [scrollState, setScrollState] = useState({ isAtBottom: true, isScrollable: false });
  const [chatLatestImageSidebarMounted, setChatLatestImageSidebarMounted] = useState(!chatLatestImageSidebarCollapsed);
  const sidebarToggleGlyphClass =
    "relative h-[11px] w-3 rounded-[4px] border-[1.2px] border-current before:absolute before:w-px before:rounded-full before:bg-current before:content-['']";

  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${textarea.scrollHeight}px`;
  }, [draft]);

  useEffect(() => {
    const updateScrollState = () => {
      const container = conversationListRef.current;
      if (!container) return;

      const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
      const nextState = {
        isAtBottom: distanceFromBottom <= 24,
        isScrollable: container.scrollHeight - container.clientHeight > 24,
      };

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
  }, [activeSession?.messages.length, highlightedMessageKey, sending]);

  useEffect(() => {
    if (!chatLatestImageSidebarCollapsed) {
      setChatLatestImageSidebarMounted(true);
      return undefined;
    }
    const timer = window.setTimeout(() => setChatLatestImageSidebarMounted(false), 240);
    return () => window.clearTimeout(timer);
  }, [chatLatestImageSidebarCollapsed]);

  const headerAvatarClass =
    "chat-header-avatar grid h-[34px] w-[34px] flex-none place-items-center rounded-full border border-black/10 object-cover";
  const agentAvatarClass =
    "message-avatar grid h-8 w-8 flex-none place-items-center overflow-hidden rounded-full border border-black/10 bg-[#f6f6f6] object-cover";
  const chatBodyClass = "text-sm leading-6";
  const chatMinorTextClass = "text-[12px]";
  const chatContentTrackClass = "mx-auto w-full max-w-[860px] px-5 md:px-6";
  const composerTrackClass = "mx-auto w-full max-w-[700px] px-5 md:px-6";
  const sidebarNavButtonClass =
    "pointer-events-auto grid h-9 w-9 place-items-center rounded-full border border-transparent bg-transparent text-[#4B5563] transition hover:border-[#C9D3DF] hover:bg-white/92 hover:text-[#1F2937] focus:outline-none focus:border-[#C9D3DF] focus:bg-white/92 disabled:cursor-default disabled:opacity-40";
  const assistantMessageBubbleClass =
    "message-bubble w-fit max-w-full rounded-[14px] border border-[rgba(228,228,228,0.66)] bg-[rgba(255,255,255,0.48)] px-3.5 py-2.5 text-left shadow-[0_1px_2px_rgba(0,0,0,0.03)] backdrop-blur-[10px] transition-colors duration-150 group-hover:bg-[rgba(255,255,255,0.72)]";
  const userMessageBubbleClass =
    "message-bubble w-fit max-w-full rounded-[14px] border border-[#E4E4E4] bg-white px-3.5 py-2.5 text-left shadow-[0_1px_2px_rgba(0,0,0,0.04)]";
  const hasIllustration = Boolean(visibleIllustrationUrl);
  const showScrollToBottom = scrollState.isScrollable && !scrollState.isAtBottom;
  const hasChatImageHistory = chatLatestImageSidebarCount > 0;
  const canGoToPreviousChatImage = chatLatestImagePosition > 1;
  const canGoToNextChatImage = hasChatImageHistory && chatLatestImagePosition < chatLatestImageSidebarCount;

  const handleComposerKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== "Enter") return;
    if (event.ctrlKey || event.shiftKey) return;
    if (event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229) return;

    event.preventDefault();
    if (!activeRoleId || !event.currentTarget.value.trim() || sending || !bridgeReady) return;
    onSendMessage(event.currentTarget.value);
  };

  const handleScrollToBottom = () => {
    const container = conversationListRef.current;
    if (!container) return;
    container.scrollTo({ top: container.scrollHeight, behavior: "smooth" });
  };

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
        {activeRole?.avatar_abs ? (
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
            {activeSession?.messages.map((message, index) => {
              const isUser = message.role === "user";
              const isError = message.role === "error";
              const authorLabel = isError ? "系统提示" : (activeRole?.name || "Agent");
              const messageKey = String(message.id ?? `${message.role}-${index}`);
              const isHighlighted = highlightedMessageKey === messageKey;
              const sourceLabel = getMessageSourceLabel(message);
              const media = Array.isArray(message.media) ? message.media : [];
              const bubbleClass = isError
                ? "message-bubble w-fit max-w-full rounded-[14px] border border-[rgba(176,58,58,0.22)] bg-[rgba(255,244,244,0.96)] px-3.5 py-2.5 text-left text-[#8f2d2d] shadow-[0_1px_2px_rgba(0,0,0,0.04)]"
                : isUser
                  ? userMessageBubbleClass
                  : assistantMessageBubbleClass;

              return (
              <article
                key={messageKey}
                data-message-key={messageKey}
                className={cx(
                  "group max-w-[82%]",
                  isHighlighted && "message-hit-anchor",
                  isUser ? "ml-auto translate-x-[2px] text-right" : "mr-auto -translate-x-[2px]",
                )}
              >
                <div className={cx("message-row flex items-start gap-3", isUser && "flex-row-reverse")}>
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
                  <div className={cx("message-body flex min-w-0 flex-col text-sm leading-6 text-[#1f1f1f]", isUser && "items-end")}>
                    {!isUser ? (
                      <div className={cx("message-author mb-1 font-medium leading-none text-[#b9b9b9]", chatMinorTextClass)}>
                        {authorLabel}
                      </div>
                    ) : null}
                    <div className={cx(bubbleClass, isHighlighted && "message-bubble-highlight ring-2 ring-[#111827]/10")}>
                      <div className="message-content whitespace-pre-wrap break-words">{message.content}</div>
                      {media.length ? (
                        <div className="mt-3 grid gap-2">
                          {media.map((item) => (
                            isChatImageAsset(item) ? (
                              <button
                                key={item}
                                className="block overflow-hidden rounded-[12px] border border-black/8 bg-white/70 p-0 text-left transition hover:bg-white focus:outline-none"
                                type="button"
                                onClick={() => onOpenChatImagePreview(item)}
                              >
                                <img className="max-h-[280px] w-full object-cover" src={toFileUrl(item)} alt="message attachment" />
                              </button>
                            ) : (
                              <a key={item} href={toFileUrl(item)} target="_blank" rel="noreferrer" className="flex items-center gap-2 rounded-[12px] border border-black/8 bg-white/70 px-3 py-2 text-[12px] text-[#4B5563] hover:bg-white">
                                <span className="font-medium">附件</span>
                                <span className="truncate">{item.split(/[\\/]/).pop() || item}</span>
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
        <div className="composer-wrap absolute inset-x-0 bottom-10 z-[2] flex min-w-0 justify-center overflow-visible">
          <div className={composerTrackClass}>
            {showScrollToBottom ? (
              <div className="pointer-events-none mb-2 flex justify-center">
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
            <div className="composer grid w-full flex-none grid-rows-[auto_auto] gap-1.5 rounded-[18px] border border-[#E4E4E4] bg-[#FFFEFF] px-3 pb-2 pt-2.5">
              <textarea
                ref={textareaRef}
                className="min-h-[24px] w-full resize-none overflow-hidden border-0 bg-transparent p-0 text-sm leading-6 text-[#1f1f1f] outline-none"
                rows={1}
                value={draft}
                onChange={(event) => onUpdateDraft(event.target.value)}
                onKeyDown={handleComposerKeyDown}
                placeholder="给当前角色发送消息..."
              />
              <div className="composer-actions flex items-center gap-2">
                <div className="composer-spacer flex-1" />
                <button className="send-btn grid h-[30px] w-[30px] cursor-pointer place-items-center rounded-full border-0 bg-[#1f1f1f] p-0 text-white disabled:cursor-default disabled:opacity-40" type="button" aria-label="发送消息" onClick={() => onSendMessage(textareaRef.current?.value)} disabled={!activeRoleId || !draft.trim() || sending || !bridgeReady}>
                  <svg className="h-[17px] w-[17px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M12 19V5" />
                    <path d="M5 12l7-7 7 7" />
                  </svg>
                </button>
              </div>
            </div>
          </div>
        </div>
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
                  <img
                    className="max-h-full max-w-full object-contain"
                    src={toFileUrl(chatLatestImagePath)}
                    alt="selected message image"
                  />
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
          </div>
        ) : null}
      </div>
    </section>
  );
}
