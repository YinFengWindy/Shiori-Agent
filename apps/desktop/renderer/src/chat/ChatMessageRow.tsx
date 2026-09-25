import React, { useCallback } from "react";
import { ChatErrorRow } from "./ChatErrorRow";
import { ChatMessageAttachments } from "./ChatMessageAttachments";
import { ChatMessageBubbleBody, hasChatMessageBubbleContent } from "./ChatMessageBubbleBody";
import {
  getChatMessageActionAvailability,
  getChatMessageSourceLabel,
} from "./chatMessageActions";
import {
  chatMessageContextMenuKeyShortcuts,
  isChatMessageContextMenuKey,
} from "./chatMessageContextMenuPlacement";
import { getChatMessageDomKey } from "./chatMessageIdentity";
import type { RoleChannelCatalog } from "../roles/roleChannelCatalog";
import { formatTimestamp, toFileUrl } from "../shared/format";
import { cx } from "../shared/styles";
import type { RoleRecord, SessionMessage } from "../shared/types";

export type ChatMessageRowProps = {
  activeRole: RoleRecord | null;
  index: number;
  /** Stable render key (see `getChatMessageReactKey`); retry targets it. */
  renderKey: string;
  isHighlighted: boolean;
  message: SessionMessage;
  /** The row was appended after this session was shown and plays the enter animation. */
  animateEnter: boolean;
  /** A reply is in flight: quoting is locked and retry waits. */
  sending: boolean;
  /** This is the latest failed turn and can be retried. */
  retryable: boolean;
  channelCatalog: RoleChannelCatalog;
  onBeginAttachmentDrag: (path: string) => void;
  onJumpToMessage: (messageKey: string) => void;
  onMeasureElement?: (message: SessionMessage, index: number, element: HTMLElement | null) => void;
  /**
   * Opens the message's context menu (复制 / 引用 / 重试): from a right-click,
   * or from the keyboard on the focused message (menu key / Shift+F10).
   */
  onOpenContextMenu: (
    event: React.MouseEvent<HTMLElement> | React.KeyboardEvent<HTMLElement>,
    message: SessionMessage,
    messageKey: string,
    sender: string,
  ) => void;
  onOpenImagePreview: (historyKey: string) => void;
  /** Retries the failed turn behind an error row (its 重试 button). */
  onRetryMessage: (renderKey: string) => void;
};

const agentAvatarClass =
  "message-avatar grid h-8 w-8 flex-none place-items-center overflow-hidden rounded-full border border-line-soft bg-surface-soft object-cover";
const chatMinorTextClass = "text-[12px]";
const assistantMessageBubbleClass =
  "message-bubble w-fit max-w-full rounded-lg border border-white/70 bg-white/80 px-3.5 py-2.5 text-left shadow-soft transition-colors duration-150 group-hover:bg-white/95";
const userMessageBubbleClass =
  "message-bubble w-fit max-w-full rounded-lg border border-line-soft bg-white px-3.5 py-2.5 text-left shadow-soft";

function RoleAvatarMark({ role }: { role: RoleRecord | null }) {
  if (role?.avatar_abs) {
    return <img className={agentAvatarClass} src={toFileUrl(role.avatar_abs)} alt={`${role.name} 的头像`} />;
  }
  return (
    <span className={cx(agentAvatarClass, "text-xs font-bold text-accent-text")}>
      {role ? role.name.slice(0, 1).toUpperCase() : "A"}
    </span>
  );
}

/** Renders one independently memoized chat message so unaffected Markdown stays out of updates. */
export const ChatMessageRow = React.memo(function ChatMessageRow({
  activeRole,
  index,
  renderKey,
  isHighlighted,
  message,
  animateEnter,
  sending,
  retryable,
  channelCatalog,
  onBeginAttachmentDrag,
  onJumpToMessage,
  onMeasureElement,
  onOpenContextMenu,
  onOpenImagePreview,
  onRetryMessage,
}: ChatMessageRowProps) {
  const isUser = message.role === "user";
  const isError = message.role === "error";
  const authorLabel = isError ? "系统提示" : (isUser ? "你" : (activeRole?.name || "角色"));
  const messageDomKey = getChatMessageDomKey(message, index);
  const sourceLabel = getChatMessageSourceLabel(message, channelCatalog);
  const availability = getChatMessageActionAvailability(message, { sending, retryable });
  const measureElement = useCallback((element: HTMLElement | null) => {
    onMeasureElement?.(message, index, element);
  }, [index, message, onMeasureElement]);
  const openContextMenu = useCallback((event: React.MouseEvent<HTMLElement> | React.KeyboardEvent<HTMLElement>) => {
    onOpenContextMenu(event, message, messageDomKey, authorLabel);
  }, [authorLabel, message, messageDomKey, onOpenContextMenu]);
  // Messages are focusable so keyboard users reach the same actions as the
  // right-click menu: the menu key or Shift+F10 opens it on the focused message.
  const openContextMenuFromKeyboard = useCallback((event: React.KeyboardEvent<HTMLElement>) => {
    if (event.defaultPrevented || !isChatMessageContextMenuKey(event)) return;
    openContextMenu(event);
  }, [openContextMenu]);
  const retry = useCallback(() => onRetryMessage(renderKey), [onRetryMessage, renderKey]);

  if (isError) {
    return (
      <article
        ref={measureElement}
        data-message-key={messageDomKey}
        className={cx("w-full rounded-md", animateEnter && "chat-message-enter")}
        tabIndex={0}
        aria-keyshortcuts={chatMessageContextMenuKeyShortcuts}
        onContextMenu={openContextMenu}
        onKeyDown={openContextMenuFromKeyboard}
      >
        <ChatErrorRow content={message.content} detail={String(message.metadata?.error_detail ?? "")} canRetry={availability.retry} onRetry={retry} />
      </article>
    );
  }

  return (
    <article
      ref={measureElement}
      data-message-key={messageDomKey}
      className={cx(
        "group w-full rounded-md",
        isHighlighted && "message-hit-anchor",
        isUser && "text-right",
        animateEnter && (isUser ? "chat-message-enter chat-message-enter-user" : "chat-message-enter"),
      )}
      tabIndex={0}
      aria-keyshortcuts={chatMessageContextMenuKeyShortcuts}
      onContextMenu={openContextMenu}
      onKeyDown={openContextMenuFromKeyboard}
    >
      <div className={cx("message-row flex w-full items-start gap-3", isUser && "flex-row-reverse justify-start")}>
        {!isUser ? <RoleAvatarMark role={activeRole} /> : null}
        <div className={cx("message-body flex min-w-0 w-full max-w-[82%] flex-col text-sm leading-6 text-ink", isUser && "ml-auto items-end")}>
          {!isUser ? (
            <div className={cx("message-author mb-1 font-medium leading-none text-ink-faint", chatMinorTextClass)}>
              {authorLabel}
            </div>
          ) : null}
          {hasChatMessageBubbleContent(message) ? (
            <div className={cx(
              isUser ? userMessageBubbleClass : assistantMessageBubbleClass,
              isUser ? "self-end" : "self-start",
              isHighlighted && "message-bubble-highlight",
            )}>
              <ChatMessageBubbleBody message={message} onJumpToMessage={onJumpToMessage} />
            </div>
          ) : null}
          <ChatMessageAttachments
            messageKey={messageDomKey}
            media={message.media}
            onBeginAttachmentDrag={onBeginAttachmentDrag}
            onOpenImagePreview={onOpenImagePreview}
          />
          {message.timestamp || sourceLabel ? (
            <div className={cx("message-time mt-1 flex items-center gap-2 text-ink-muted opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100", chatMinorTextClass)}>
              {message.timestamp ? <span>{formatTimestamp(message.timestamp)}</span> : null}
              {sourceLabel ? <span>{`来自${sourceLabel}`}</span> : null}
            </div>
          ) : null}
        </div>
      </div>
    </article>
  );
});
