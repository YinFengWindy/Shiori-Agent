import React, { useEffect, useEffectEvent, useRef, useState } from "react";
import { Stop } from "@phosphor-icons/react";
import { ChatComposerAttachments } from "./ChatComposerAttachments";
import { ChatComposerReplyTarget } from "./ChatComposerReplyTarget";
import { ChatEmojiPicker } from "./ChatEmojiPicker";
import { getChatComposerLimits } from "./chatComposerLayout";
import { canSubmitChatMessage } from "./chatComposerState";
import { insertEmojiIntoChatDraft } from "./chatEmojiState";
import { PlusIcon, SendIcon } from "../shared/icons";
import type { ChatSendRequest } from "../shared/types";
import { AutosizeTextarea, compactPressableClass, cx, errorMessage } from "@yinfengwindy/shiori-sdk";
import { mascotFeedback as feedback } from "../shared/mascot/mascotFeedback";
import { appendImportedChatAttachments, getChatDraftKey, submitChatDraft, updateChatDraft } from "./chatDraftStore";
import { useChatDraft } from "./useChatDraft";
import { ChatModelMenu } from "./ChatModelMenu";
import { ChatContextRing } from "./ChatContextRing";
import { useChatContext } from "./useChatContext";
import { isCompactCommand } from "./chatContextActions";

/** Shared by send and stop so swapping between them keeps the same press feel. */
const sendButtonClass = cx(
  compactPressableClass,
  "send-btn grid h-[30px] w-[30px] flex-none cursor-pointer place-items-center rounded-full border-0 bg-gradient-accent p-0 text-ink shadow-soft hover:brightness-105 disabled:cursor-default disabled:opacity-40",
);

type ChatComposerProps = {
  activeRoleId: string;
  sessionKey: string;
  bridgeReady: boolean;
  sending: boolean;
  cancelling: boolean;
  /** Height of the chat pane the composer floats in; 0 until measured. */
  paneHeight?: number;
  onSendMessage: (request: ChatSendRequest) => Promise<boolean>;
  onCancelChat: () => void;
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
  paneHeight = 0,
  onSendMessage,
  onCancelChat,
  onJumpToMessage,
  onHeightChange,
}: ChatComposerProps) {
  const composerRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const pendingSelectionRef = useRef<{ start: number; end: number } | null>(null);
  const draftKey = getChatDraftKey(activeRoleId);
  const { content: draft, attachments: pendingAttachments, replyTarget } = useChatDraft(draftKey);
  const [emojiPickerOpen, setEmojiPickerOpen] = useState(false);
  const context = useChatContext(activeRoleId, sessionKey, bridgeReady, sending);
  const canSubmit = canSubmitChatMessage(draft, pendingAttachments);
  const composerInputDisabled = !activeRoleId || sending || !bridgeReady;
  const limits = getChatComposerLimits(paneHeight);
  const reportHeight = useEffectEvent((height: number) => onHeightChange?.(height));

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea || !pendingSelectionRef.current) return;
    textarea.focus();
    textarea.setSelectionRange(pendingSelectionRef.current.start, pendingSelectionRef.current.end);
    pendingSelectionRef.current = null;
  }, [draft]);

  useEffect(() => {
    setEmojiPickerOpen(false);
    pendingSelectionRef.current = null;
  }, [draftKey]);

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

  function setDraft(content: string): void {
    updateChatDraft(draftKey, (current) => current.content === content ? current : { ...current, content });
  }

  function clearReplyTarget(): void {
    updateChatDraft(draftKey, (current) => ({ ...current, replyTarget: null }));
  }

  async function addAttachments(importFiles: () => Promise<string[]>): Promise<void> {
    if (composerInputDisabled) return;
    try {
      const paths = await importFiles();
      if (!paths.length) return;
      // This closure retains the initiating session even after navigation or unmount.
      appendImportedChatAttachments(draftKey, paths);
    } catch (error) {
      feedback.error(`附件导入失败：${errorMessage(error)}`);
    }
  }

  function handleDragOver(event: React.DragEvent<HTMLDivElement>): void {
    if (!event.dataTransfer.types.includes("Files")) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = composerInputDisabled ? "none" : "copy";
  }

  function handleDrop(event: React.DragEvent<HTMLDivElement>): void {
    if (!event.dataTransfer.types.includes("Files")) return;
    // Never let a file navigate the renderer or insert its local URL into the text.
    event.preventDefault();
    const files = Array.from(event.dataTransfer.files);
    if (!files.length) return;
    void addAttachments(() => window.miraDesktop.importChatImages(files));
  }

  function removePendingAttachment(path: string): void {
    updateChatDraft(draftKey, (current) => ({ ...current, attachments: current.attachments.filter((item) => item !== path) }));
  }

  async function submitMessage(): Promise<void> {
    if (!activeRoleId || !bridgeReady || sending || !canSubmit) {
      return;
    }
    if (isCompactCommand(draft)) {
      await context.compact();
      return;
    }
    setEmojiPickerOpen(false);
    try {
      await submitChatDraft(draftKey, onSendMessage);
    } catch (error) {
      feedback.error(`消息发送失败：${errorMessage(error)}`);
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
          onDragOver={handleDragOver}
          onDrop={handleDrop}
          className="composer grid min-w-0 w-full grid-cols-[minmax(0,1fr)] flex-none gap-1.5 overflow-hidden rounded-lg border border-white/75 bg-white/90 px-3 pb-2 pt-2.5 shadow-panel backdrop-blur-lg"
          style={{ maxHeight: limits.composerMaxHeight }}
        >
          {replyTarget ? (
            <ChatComposerReplyTarget
              replyTarget={replyTarget}
              disabled={sending}
              onClear={clearReplyTarget}
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
          <div className="composer-actions flex min-w-0 items-center gap-2">
            <button
              className="grid h-[30px] w-[30px] flex-none place-items-center rounded-full border-0 bg-transparent p-0 text-ink-secondary transition hover:bg-accent-softer hover:text-accent-text focus:outline-none disabled:cursor-default disabled:opacity-40"
              type="button"
              aria-label="添加附件"
              onClick={() => void addAttachments(() => window.miraDesktop.pickChatAttachments({ multiple: true }))}
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
            <ChatContextRing status={context.status} busy={context.busy} notice={context.notice} unavailable={context.unavailable} onCompact={context.compact} />
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
