import type React from "react";
import { formatTimestamp, toFileUrl } from "../shared/format";
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
  return (
    <section className="chat-surface">
      <header className="chat-header" data-testid="session-hero">
        {activeRole?.avatar_abs ? (
          <img
            className="chat-header-avatar"
            src={toFileUrl(activeRole.avatar_abs)}
            alt={`${activeRole.name} avatar`}
          />
        ) : (
          <span className="chat-header-avatar chat-header-avatar-fallback">
            {activeRole ? activeRole.name.slice(0, 1).toUpperCase() : "M"}
          </span>
        )}
        <div className="chat-header-title">{activeRole ? activeRole.name : "Select a role"}</div>
      </header>
      <section
        className="conversation-panel"
        style={visibleIllustrationUrl ? {
          backgroundImage: `linear-gradient(rgba(255, 255, 255, 0.82), rgba(255, 255, 255, 0.82)), url("${visibleIllustrationUrl}")`,
        } : undefined}
      >
        {notice ? <div className="notice-chip">{notice}</div> : null}
        <div className="conversation-list">
          {activeSession?.messages.length ? activeSession.messages.map((message, index) => (
            <article key={`${message.id ?? message.role}-${index}`} className={`bubble bubble-${message.role}`}>
              <div className="bubble-role">{message.role}</div>
              <div className="bubble-content">{message.content}</div>
              {message.timestamp ? <div className="bubble-time">{formatTimestamp(message.timestamp)}</div> : null}
            </article>
          )) : (
            <div className="empty-card">No messages yet. Send the first message to this role.</div>
          )}
          <div ref={conversationEndRef} />
        </div>
        <div className="composer-wrap">
          <div className="composer">
            <textarea
              value={draft}
              onChange={(event) => onUpdateDraft(event.target.value)}
              placeholder="Type a message for this role..."
            />
            <div className="composer-actions">
              <button className="composer-tool-btn" type="button" aria-label="Add attachment">
                <span />
              </button>
              <div className="composer-spacer" />
              <button className="ghost-btn composer-cancel" type="button" onClick={onCancelMessage} disabled={!activeRoleId || !sending || !bridgeReady}>
                Cancel
              </button>
              <button className="send-btn" type="button" aria-label="Send message" onClick={onSendMessage} disabled={!activeRoleId || !draft.trim() || sending || !bridgeReady}>
                <span />
              </button>
            </div>
          </div>
        </div>
      </section>
    </section>
  );
}
