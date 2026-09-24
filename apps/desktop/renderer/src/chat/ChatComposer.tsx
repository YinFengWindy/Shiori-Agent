import React, { useEffect, useEffectEvent, useRef, useState } from "react";
import { Stop } from "@phosphor-icons/react";
import { ChatComposerAttachments } from "./ChatComposerAttachments";
import { ChatComposerReplyTarget } from "./ChatComposerReplyTarget";
import { ChatEmojiPicker } from "./ChatEmojiPicker";
import { getChatComposerLimits } from "./chatComposerLayout";
import { canSubmitChatMessage, normalizeChatAttachmentPaths } from "./chatComposerState";
import { insertEmojiIntoChatDraft } from "./chatEmojiState";
import { PlusIcon, SendIcon } from "../shared/icons";
import type { ChatReplyTarget, ChatSendRequest } from "../shared/types";
import { AutosizeTextarea } from "../shared/AutosizeTextarea";
import { ChatModelMenu } from "./ChatModelMenu";
import { compactPressableClass, cx } from "../shared/styles";

/** Shared by send and stop so swapping between them keeps the same press feel. */
const sendButtonClass = cx(
  compactPressableClass,
  "send-btn grid h-[30px] w-[30px] cursor-pointer place-items-center rounded-full border-0 bg-gradient-accent p-0 text-ink shadow-soft hover:brightness-105 disabled:cursor-default disabled:opacity-40",
);

/** Text the surface asks the composer to put in the draft (e.g. an empty-state suggestion); `id` makes repeats distinct. */
export type ChatComposerDraftRequest = { text: string; id: number };

type ChatComposerProps = {
  activeRoleId: string;
  sessionKey: string;
  bridgeReady: boolean;
  sending: boolean;
  cancelling: boolean;
  replyTarget: ChatReplyTarget | null;
  /** Height of the chat pane the composer floats in; 0 until measured. */
  paneHeight?: number;
  draftRequest?: ChatComposerDraftRequest | null;
  onSendMessage: (request: ChatSendRequest) => Promise<boolean>;
  onCancelChat: () => void;
  onClearReplyTarget: () => void;
  onJumpToMessage: (messageKey: string) => void;
  /** Reports the composer card's rendered height so the message list can keep clear of it. */
  onHeightChange?: (height: number) => void;
};

/** Owns draft, pending attachments, and reply target rendering for the desktop chat composer. */
export const ChatComposer = React.memo(function ChatComposer({
  activeRoleId,
  sessionKey,
  bridgeReady,
  sending,
  cancelling,
  replyTarget,
  paneHeight = 0,
  draftRequest = null,
  onSendMessage,
  onCancelChat,
  onClearReplyTarget,
  onJumpToMessage,
  onHeightChange,
}: ChatComposerProps) {
  const composerRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const pendingSelectionRef = useRef<{ start: number; end: number } | null>(null);
  const [draft, setDraft] = useState("");
  const [emojiPickerOpen, setEmojiPickerOpen] = useState(false);
  const [pendingAttachments, setPendingAttachments] = useState<string[]>([]);
  const canSubmit = canSubmitChatMessage(draft, pendingAttachments);
  const composerInputDisabled = !activeRoleId || sending || !bridgeReady;
  const limits = getChatComposerLimits(paneHeight);
  const clearReplyTargetForSessionChange = useEffectEvent(onClearReplyTarget);
  const reportHeight = useEffectEvent((height: number) => onHeightChange?.(height));

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea || !pendingSelectionRef.current) return;
    textarea.focus();
    textarea.setSelectionRange(pendingSelectionRef.current.start, pendingSelectionRef.current.end);
    pendingSelectionRef.current = null;
  }, [draft]);

  useEffect(() => {
    setDraft("");
    setEmojiPickerOpen(false);
    pendingSelectionRef.current = null;
    setPendingAttachments([]);
    clearReplyTargetForSessionChange();
  }, [activeRoleId, sessionKey]);

  useEffect(() => {
    if (!draftRequest) return;
    pendingSelectionRef.current = { start: draftRequest.text.length, end: draftRequest.text.length };
    setDraft(draftRequest.text);
  }, [draftRequest]);

  useEffect(() => {
    if (sending) {
      setEmojiPickerOpen(false);
    }
  }, [sending]);

  useEffect(() => {
    const composer = composerRef.current;
    if (!composer || typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(() => reportHeight(composer.offsetHeight));
    observer.observe(composer);
    reportHeight(composer.offsetHeight);
    return () => observer.disconnect();
  }, []);

  async function pickChatAttachments(): Promise<void> {
    const files = await window.miraDesktop.pickChatAttachments({ multiple: true });
    if (!files.length) {
      return;
    }
    setPendingAttachments((current) => normalizeChatAttachmentPaths([...current, ...files]));
  }

  function removePendingAttachment(path: string): void {
    setPendingAttachments((current) => current.filter((item) => item !== path));
  }

  async function submitMessage(): Promise<void> {
    if (!activeRoleId || !bridgeReady || sending || !canSubmit) {
      return;
    }
    setEmojiPickerOpen(false);
    const request: ChatSendRequest = {
      content: draft,
      attachments: pendingAttachments,
      replyTarget,
    };
    setDraft("");
    setPendingAttachments([]);
    onClearReplyTarget();
    const sent = await onSendMessage(request);
    if (!sent) {
      setDraft(request.content);
      setPendingAttachments(request.attachments);
    }
  }

  function handleSelectEmoji(emoji: string): void {
    const nextDraft = insertEmojiIntoChatDraft(
      draft,
      emoji,
      textareaRef.current?.selectionStart,
      textareaRef.current?.selectionEnd,
    );
    pendingSelectionRef.current = {
      start: nextDraft.selectionStart,
      end: nextDraft.selectionEnd,
    };
    setDraft(nextDraft.value);
    setEmojiPickerOpen(false);
  }

  function handleComposerKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter") return;
    if (event.ctrlKey || event.shiftKey) return;
    if (event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229) return;
    event.preventDefault();
    void submitMessage();
  }

  return (
    <div className="composer-wrap pointer-events-none absolute inset-x-0 bottom-10 z-[2] flex min-w-0 justify-center overflow-visible">
      <div className="pointer-events-auto mx-auto w-full max-w-[700px] px-5 md:px-6">
        <div
          ref={composerRef}
          className="composer grid w-full flex-none gap-1.5 overflow-hidden rounded-lg border border-white/75 bg-white/90 px-3 pb-2 pt-2.5 shadow-panel backdrop-blur-lg"
          style={{ maxHeight: limits.composerMaxHeight }}
        >
          {replyTarget ? (
            <ChatComposerReplyTarget
              replyTarget={replyTarget}
              disabled={sending}
              onClear={onClearReplyTarget}
              onJumpToMessage={onJumpToMessage}
            />
          ) : null}
          <ChatComposerAttachments
            paths={pendingAttachments}
            disabled={sending}
            maxHeight={limits.attachmentsMaxHeight}
            onRemove={removePendingAttachment}
          />
          {/* Borderless by design (`ring-0` / `focus:shadow-none`): the card itself is the field. */}
          <AutosizeTextarea
            ref={textareaRef}
            className="min-h-[24px] w-full overflow-y-auto border-0 bg-transparent p-0 text-sm leading-6 text-ink outline-none placeholder:text-ink-faint focus:shadow-none"
            style={{ maxHeight: limits.textareaMaxHeight }}
            containerClassName="min-h-[24px] overflow-hidden"
            containerStyle={{ maxHeight: limits.textareaMaxHeight }}
            mirrorClassName="min-h-[24px] text-sm leading-6"
            rows={1}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleComposerKeyDown}
            placeholder="给当前角色发送消息..."
          />
          <div className="composer-actions flex items-center gap-2">
            <button
              className="grid h-[30px] w-[30px] place-items-center rounded-full border-0 bg-transparent p-0 text-ink-secondary transition hover:bg-accent-softer hover:text-accent-text focus:outline-none disabled:cursor-default disabled:opacity-40"
              type="button"
              aria-label="添加附件"
              onClick={() => void pickChatAttachments()}
              disabled={composerInputDisabled}
            >
              <PlusIcon className="h-[14px] w-[14px] fill-current" />
            </button>
            <ChatModelMenu activeRoleId={activeRoleId} bridgeReady={bridgeReady} />
            <div className="composer-spacer flex-1" />
            <ChatEmojiPicker
              disabled={composerInputDisabled}
              open={emojiPickerOpen}
              onClose={() => setEmojiPickerOpen(false)}
              onSelectEmoji={handleSelectEmoji}
              onToggle={() => setEmojiPickerOpen((current) => !current)}
            />
            {/* One button whose icon crossfades between send and stop, so focus and press state survive the swap. */}
            <button
              className={sendButtonClass}
              type="button"
              aria-label={sending ? "中止回复" : "发送消息"}
              onClick={sending ? onCancelChat : () => void submitMessage()}
              disabled={sending ? cancelling : !activeRoleId || !canSubmit || !bridgeReady}
            >
              <span className="relative grid h-[15px] w-[15px] place-items-center" aria-hidden="true">
                <SendIcon className={cx("chat-send-icon absolute inset-0 h-[15px] w-[15px] fill-current", sending && "chat-send-icon-hidden")} />
                <Stop className={cx("chat-send-icon absolute inset-0 h-[15px] w-[15px] fill-current", !sending && "chat-send-icon-hidden")} />
              </span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
});
