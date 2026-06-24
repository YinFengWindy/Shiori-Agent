import type React from "react";
import { useLayoutEffect, useRef } from "react";
import { formatTimestamp, toFileUrl } from "../shared/format";
import { bodyTextClass, cardClass, cx, ghostButtonClass } from "../shared/styles";
import type { RoleRecord, SessionPayload } from "../shared/types";

type ChatSurfaceProps = {
  activeRole: RoleRecord | null;
  activeRoleId: string;
  activeSession: SessionPayload | null;
  bridgeReady: boolean;
  conversationEndRef: React.RefObject<HTMLDivElement | null>;
  draft: string;
  notice: string;
  sending: boolean;
  visibleIllustrationUrl: string;
  onCancelMessage: () => void;
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
  notice,
  sending,
  visibleIllustrationUrl,
  onCancelMessage,
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

  return (
    <section className="chat-surface grid h-full min-h-0 grid-rows-chat bg-[var(--chat-bg)]">
      <header className="chat-header flex min-w-0 items-center gap-3 border-b border-[rgba(163,171,212,0.28)] bg-[var(--chat-bg)] pl-[23px] pr-6" data-testid="session-hero">
        {activeRole?.avatar_abs ? (
          <img
            className={headerAvatarClass}
            src={toFileUrl(activeRole.avatar_abs)}
            alt={`${activeRole.name} avatar`}
          />
        ) : (
          <span className={cx(headerAvatarClass, "chat-header-avatar-fallback bg-[#f6f6f6] text-xs font-bold text-[#333333]")}>
            {activeRole ? activeRole.name.slice(0, 1).toUpperCase() : "M"}
          </span>
        )}
        <div className="chat-header-title min-w-0 flex-1 truncate text-xs font-semibold text-[#1f1f1f]">{activeRole ? activeRole.name : "Select a role"}</div>
      </header>
      <section
        className="conversation-panel grid h-full min-h-0 grid-rows-conversation overflow-hidden bg-[var(--chat-bg)] bg-contain bg-center bg-no-repeat"
        style={visibleIllustrationUrl ? {
          backgroundImage: `linear-gradient(rgba(247, 248, 255, 0.84), rgba(247, 248, 255, 0.84)), url("${visibleIllustrationUrl}")`,
        } : undefined}
      >
        {notice ? <div className="notice-chip rounded-[14px] border border-[rgba(26,106,58,0.18)] bg-[rgba(26,106,58,0.08)] px-3.5 py-2.5 text-[#1a6a3a]">{notice}</div> : null}
        <div className={cx("conversation-list scrollbar-soft scrollbar-soft-muted grid min-h-0 content-start gap-3 overflow-auto px-6 pb-5 pt-7 md:px-12 lg:px-20 xl:px-[132px]", bodyTextClass)}>
          {activeSession?.messages.length ? activeSession.messages.map((message, index) => (
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
                <div className={cx("message-body flex min-w-0 flex-col text-xs leading-5 text-[#1f1f1f]", message.role === "user" && "items-end")}>
                  {message.role !== "user" ? (
                    <div className="message-author mb-1 text-[11px] font-medium leading-none text-[#b9b9b9]">
                      {activeRole?.name || "Agent"}
                    </div>
                  ) : null}
                  <div className="message-content whitespace-pre-wrap break-words">{message.content}</div>
                  {message.timestamp ? (
                    <div className="message-time mt-1 text-[11px] text-muted opacity-0 transition-opacity duration-150 group-hover:opacity-100">
                      {formatTimestamp(message.timestamp)}
                    </div>
                  ) : null}
                </div>
              </div>
            </article>
          )) : (
            <div className={cx("empty-card", cardClass, "p-4")}>No messages yet. Send the first message to this role.</div>
          )}
          <div ref={conversationEndRef} />
        </div>
        <div className="composer-wrap flex min-h-0 min-w-0 items-end justify-center overflow-visible px-6 pb-[22px]">
          <div className="composer grid w-full max-w-[550px] flex-none grid-rows-[auto_auto] gap-1.5 rounded-[18px] border border-[#e4e4e4] bg-white px-3 pb-2 pt-2.5">
            <textarea
              ref={textareaRef}
              className="min-h-[24px] w-full resize-none overflow-hidden border-0 bg-transparent p-0 text-xs leading-5 text-[#1f1f1f] outline-none"
              rows={1}
              value={draft}
              onChange={(event) => onUpdateDraft(event.target.value)}
              placeholder="Type a message for this role..."
            />
            <div className="composer-actions flex items-center gap-2">
              <button className="composer-tool-btn grid h-7 w-7 cursor-pointer place-items-center rounded-full border-0 bg-transparent p-0 text-[#8a8a8a] hover:bg-[#f5f5f5] focus-visible:bg-[#f5f5f5]" type="button" aria-label="Add attachment">
                <span className="relative h-4 w-4 before:absolute before:left-[7px] before:top-px before:h-3.5 before:w-[1.5px] before:rounded-full before:bg-current before:content-[''] after:absolute after:left-px after:top-[7px] after:h-[1.5px] after:w-3.5 after:rounded-full after:bg-current after:content-['']" />
              </button>
              <div className="composer-spacer flex-1" />
              <button className={cx("ghost-btn composer-cancel px-3 py-1.5 text-xs disabled:hidden", ghostButtonClass)} type="button" onClick={onCancelMessage} disabled={!activeRoleId || !sending || !bridgeReady}>
                Cancel
              </button>
              <button className="send-btn grid h-[30px] w-[30px] cursor-pointer place-items-center rounded-full border-0 bg-[#1f1f1f] p-0 text-white disabled:cursor-default disabled:opacity-40" type="button" aria-label="Send message" onClick={onSendMessage} disabled={!activeRoleId || !draft.trim() || sending || !bridgeReady}>
                <span className="relative h-[18px] w-4 before:absolute before:left-[7px] before:top-[3px] before:h-[13px] before:w-0.5 before:rounded-full before:bg-current before:content-[''] after:absolute after:left-[3px] after:top-0.5 after:h-2 after:w-2 after:rotate-45 after:border-l-2 after:border-t-2 after:border-current after:content-['']" />
              </button>
            </div>
          </div>
        </div>
      </section>
    </section>
  );
}
