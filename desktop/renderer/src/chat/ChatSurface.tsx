import type React from "react";
import { useLayoutEffect, useRef } from "react";
import { formatTimestamp, toFileUrl } from "../shared/format";
import { cx, ghostButtonClass } from "../shared/styles";
import type { RoleRecord, SessionPayload } from "../shared/types";

type ChatSurfaceProps = {
  activeRole: RoleRecord | null;
  activeRoleId: string;
  activeSession: SessionPayload | null;
  bridgeReady: boolean;
  conversationEndRef: React.RefObject<HTMLDivElement | null>;
  draft: string;
  headerTitle: string;
  notice: string;
  sending: boolean;
  visibleIllustrationUrl: string;
  onSendMessage: () => void;
  onUpdateDraft: (value: string) => void;
};

/** Renders the active role chat header, conversation messages, and composer. */
export function ChatSurface({
  activeRole,
  activeRoleId,
  activeSession,
  bridgeReady,
  conversationEndRef,
  draft,
  headerTitle,
  notice,
  sending,
  visibleIllustrationUrl,
  onSendMessage,
  onUpdateDraft,
}: ChatSurfaceProps) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${textarea.scrollHeight}px`;
  }, [draft]);

  const headerAvatarClass =
    "chat-header-avatar grid h-[34px] w-[34px] flex-none place-items-center rounded-full border border-black/10 object-cover";
  const agentAvatarClass =
    "message-avatar grid h-8 w-8 flex-none place-items-center overflow-hidden rounded-full border border-black/10 bg-[#f6f6f6] object-cover";
  const chatBodyClass = "text-sm leading-6";
  const chatMinorTextClass = "text-[12px]";
  const chatContentTrackClass = "mx-auto w-full max-w-[860px] px-5 md:px-6";
  const composerTrackClass = "mx-auto w-full max-w-[700px] px-5 md:px-6";
  const messageBubbleClass =
    "message-bubble w-fit max-w-full rounded-[14px] border border-[#E4E4E4] bg-white px-3.5 py-2.5 text-left shadow-[0_1px_2px_rgba(0,0,0,0.04)]";
  const hasIllustration = Boolean(visibleIllustrationUrl);

  const handleComposerKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== "Enter") return;
    if (event.ctrlKey || event.shiftKey) return;
    if (event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229) return;

    event.preventDefault();
    if (!activeRoleId || !draft.trim() || sending || !bridgeReady) return;
    onSendMessage();
  };

  return (
    <section className="chat-surface relative grid h-full min-h-0 grid-rows-chat overflow-hidden bg-[var(--chat-bg)]">
      {hasIllustration ? (
        <div
          className="conversation-illustration pointer-events-none absolute inset-0 z-0 overflow-hidden"
          aria-hidden="true"
        >
          <div
            className="conversation-illustration-image absolute inset-0 bg-cover bg-center bg-no-repeat opacity-[0.96]"
            style={{ backgroundImage: `url("${visibleIllustrationUrl}")` }}
          />
          <div className="conversation-illustration-fade absolute inset-0 bg-[linear-gradient(90deg,rgba(255,255,255,0.96)_0%,rgba(255,255,255,0.92)_32%,rgba(255,255,255,0.72)_56%,rgba(255,255,255,0.32)_76%,rgba(255,255,255,0.08)_100%)]" />
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
        {notice ? <div className="notice-chip absolute left-1/2 top-4 z-[2] -translate-x-1/2 rounded-[14px] border border-[rgba(26,106,58,0.18)] bg-[rgba(26,106,58,0.08)] px-3.5 py-2.5 text-[#1a6a3a]">{notice}</div> : null}
        <div
          className={cx(
            "conversation-list scrollbar-soft scrollbar-soft-muted relative z-[1] h-full min-h-0 overflow-auto pb-5 pt-7",
            chatBodyClass,
          )}
        >
          <div className={cx("grid content-start gap-3", chatContentTrackClass)}>
            {activeSession?.messages.map((message, index) => (
              <article
                key={`${message.id ?? message.role}-${index}`}
                className={cx(
                  "group max-w-[82%]",
                  message.role === "user" ? "ml-auto translate-x-[2px] text-right" : "mr-auto -translate-x-[2px]",
                )}
              >
                <div className={cx("message-row flex items-start gap-3", message.role === "user" && "flex-row-reverse")}>
                  {message.role !== "user" ? (
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
                  <div className={cx("message-body flex min-w-0 flex-col text-sm leading-6 text-[#1f1f1f]", message.role === "user" && "items-end")}>
                    {message.role !== "user" ? (
                      <div className={cx("message-author mb-1 font-medium leading-none text-[#b9b9b9]", chatMinorTextClass)}>
                        {activeRole?.name || "Agent"}
                      </div>
                    ) : null}
                    <div className={messageBubbleClass}>
                      <div className="message-content whitespace-pre-wrap break-words">{message.content}</div>
                    </div>
                    {message.timestamp ? (
                      <div className={cx("message-time mt-1 text-muted opacity-0 transition-opacity duration-150 group-hover:opacity-100", chatMinorTextClass)}>
                        {formatTimestamp(message.timestamp)}
                      </div>
                    ) : null}
                  </div>
                </div>
              </article>
            ))}
            <div ref={conversationEndRef} className="h-40" />
          </div>
        </div>
        <div className="composer-wrap absolute inset-x-0 bottom-10 z-[2] flex min-w-0 justify-center overflow-visible">
          <div className={composerTrackClass}>
            <div className="composer grid w-full flex-none grid-rows-[auto_auto] gap-1.5 rounded-[18px] border border-[#E4E4E4] bg-[#FFFEFF] px-3 pb-2 pt-2.5">
              <textarea
                ref={textareaRef}
                className="min-h-[24px] w-full resize-none overflow-hidden border-0 bg-transparent p-0 text-sm leading-6 text-[#1f1f1f] outline-none"
                rows={1}
                value={draft}
                onChange={(event) => onUpdateDraft(event.target.value)}
                onKeyDown={handleComposerKeyDown}
                placeholder="Type a message for this role..."
              />
              <div className="composer-actions flex items-center gap-2">
                <div className="composer-spacer flex-1" />
                {sending ? <div className="composer-status px-1 text-[12px] text-[#6f6f6f]">正在输入中...</div> : null}
                <button className="send-btn grid h-[30px] w-[30px] cursor-pointer place-items-center rounded-full border-0 bg-[#1f1f1f] p-0 text-white disabled:cursor-default disabled:opacity-40" type="button" aria-label="Send message" onClick={onSendMessage} disabled={!activeRoleId || !draft.trim() || sending || !bridgeReady}>
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
    </section>
  );
}
