import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { canSubmitChatMessage, normalizeChatAttachmentPaths } from "./chatComposerState";
import { isChatImageAsset } from "./chatImageHistory";
import { DeleteIcon, DocumentIcon, PlusIcon, SendIcon } from "../shared/icons";
import { toFileUrl } from "../shared/format";
import type { ChatReplyTarget, ChatSendRequest } from "../shared/types";

type ChatComposerProps = {
  activeRoleId: string;
  sessionKey: string;
  bridgeReady: boolean;
  sending: boolean;
  replyTarget: ChatReplyTarget | null;
  onSendMessage: (request: ChatSendRequest) => Promise<boolean>;
  onClearReplyTarget: () => void;
  onJumpToMessage: (messageKey: string) => void;
};

function getAttachmentName(path: string): string {
  return path.split(/[\\/]/).pop() || path;
}

function getAttachmentExtensionLabel(path: string): string {
  const attachmentName = getAttachmentName(path);
  const dotIndex = attachmentName.lastIndexOf(".");
  if (dotIndex < 0 || dotIndex === attachmentName.length - 1) {
    return "FILE";
  }
  return attachmentName.slice(dotIndex + 1).toUpperCase();
}

/** Owns draft, pending attachments, and reply target rendering for the desktop chat composer. */
export function ChatComposer({
  activeRoleId,
  sessionKey,
  bridgeReady,
  sending,
  replyTarget,
  onSendMessage,
  onClearReplyTarget,
  onJumpToMessage,
}: ChatComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const [draft, setDraft] = useState("");
  const [pendingAttachments, setPendingAttachments] = useState<string[]>([]);
  const canSubmit = canSubmitChatMessage(draft, pendingAttachments);

  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${textarea.scrollHeight}px`;
  }, [draft]);

  useEffect(() => {
    setDraft("");
    setPendingAttachments([]);
    onClearReplyTarget();
  }, [activeRoleId, onClearReplyTarget, sessionKey]);

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

  function handleComposerKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter") return;
    if (event.ctrlKey || event.shiftKey) return;
    if (event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229) return;
    event.preventDefault();
    void submitMessage();
  }

  return (
    <div className="composer-wrap absolute inset-x-0 bottom-10 z-[2] flex min-w-0 justify-center overflow-visible">
      <div className="mx-auto w-full max-w-[700px] px-5 md:px-6">
        <div className="composer grid w-full flex-none gap-1.5 rounded-[18px] border border-[#E4E4E4] bg-[#FFFEFF] px-3 pb-2 pt-2.5">
          {replyTarget ? (
            <div className="flex min-w-0 items-start gap-2 rounded-md border border-[#E5E7EB] bg-[#F8FAFC] px-2.5 py-2 text-left">
              {replyTarget.messageId ? (
                <button
                  className="min-w-0 flex-1 border-0 bg-transparent p-0 text-left transition hover:opacity-85 focus:outline-none"
                  type="button"
                  aria-label="跳转到引用来源消息"
                  onClick={() => onJumpToMessage(replyTarget.messageId)}
                >
                  <div className="border-l-2 border-[#AEB7C5] pl-2.5">
                    <div className="truncate text-[11px] font-medium leading-4 text-[#6B7280]">{replyTarget.sender || "历史消息"}</div>
                    <div className="line-clamp-2 text-[12px] leading-5 text-[#4B5563]">{replyTarget.preview}</div>
                  </div>
                </button>
              ) : (
                <div className="min-w-0 flex-1 border-l-2 border-[#AEB7C5] pl-2.5">
                  <div className="truncate text-[11px] font-medium leading-4 text-[#6B7280]">{replyTarget.sender || "历史消息"}</div>
                  <div className="line-clamp-2 text-[12px] leading-5 text-[#4B5563]">{replyTarget.preview}</div>
                </div>
              )}
              <button
                className="grid h-6 w-6 flex-none place-items-center rounded-md border-0 bg-transparent p-0 text-[#7C8797] transition hover:bg-black/5 hover:text-[#1F2937] focus:outline-none disabled:cursor-default disabled:opacity-40"
                type="button"
                aria-label="取消引用"
                onClick={onClearReplyTarget}
                disabled={sending}
              >
                <DeleteIcon className="h-[10px] w-[10px] fill-current" />
              </button>
            </div>
          ) : null}
          {pendingAttachments.length ? (
            <div className="flex flex-wrap gap-2">
              {pendingAttachments.map((path) => (
                isChatImageAsset(path) ? (
                  <span
                    key={path}
                    className="relative h-14 w-14 overflow-hidden rounded-md border border-black/8 bg-[#F6F7FA]"
                  >
                    <img
                      className="h-full w-full object-cover"
                      src={toFileUrl(path)}
                      alt=""
                    />
                    <button
                      className="absolute right-1 top-1 grid h-4 w-4 place-items-center rounded-full bg-white/92 p-0 text-[#7C8797] shadow-[0_4px_12px_rgba(15,23,42,0.12)] transition hover:text-[#1F2937] focus:outline-none disabled:cursor-default disabled:opacity-40"
                      type="button"
                      aria-label="移除图片附件"
                      onClick={() => removePendingAttachment(path)}
                      disabled={sending}
                    >
                      <DeleteIcon className="h-[10px] w-[10px] fill-current" />
                    </button>
                  </span>
                ) : (
                  <span
                    key={path}
                    className="relative inline-flex max-w-[220px] items-center gap-2 rounded-[16px] border border-black/8 bg-[#F6F7FA] px-3 py-2 text-left text-[#4B5563]"
                  >
                    <span className="grid h-9 w-9 flex-none place-items-center rounded-[12px] bg-white text-[#6B7280] shadow-[inset_0_0_0_1px_rgba(15,23,42,0.06)]">
                      <DocumentIcon className="h-4 w-4 stroke-current" />
                    </span>
                    <span className="min-w-0 flex-1 pr-4">
                      <span className="block truncate text-[12px] font-medium leading-[1.2] text-[#1F2937]">
                        {getAttachmentName(path)}
                      </span>
                      <span className="mt-1 block text-[11px] leading-none text-[#8B95A7]">
                        {getAttachmentExtensionLabel(path)}
                      </span>
                    </span>
                    <button
                      className="absolute right-2 top-2 grid h-4 w-4 place-items-center rounded-full border-0 bg-transparent p-0 text-[#7C8797] transition hover:text-[#1F2937] focus:outline-none disabled:cursor-default disabled:opacity-40"
                      type="button"
                      aria-label={`移除附件 ${getAttachmentName(path)}`}
                      onClick={() => removePendingAttachment(path)}
                      disabled={sending}
                    >
                      <DeleteIcon className="h-[10px] w-[10px] fill-current" />
                    </button>
                  </span>
                )
              ))}
            </div>
          ) : null}
          <textarea
            ref={textareaRef}
            className="min-h-[24px] w-full resize-none overflow-hidden border-0 bg-transparent p-0 text-sm leading-6 text-[#1f1f1f] outline-none"
            rows={1}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleComposerKeyDown}
            placeholder="给当前角色发送消息..."
          />
          <div className="composer-actions flex items-center gap-2">
            <button
              className="grid h-[30px] w-[30px] place-items-center rounded-full border-0 bg-transparent p-0 text-[#4B5563] transition focus:outline-none disabled:cursor-default disabled:opacity-40"
              type="button"
              aria-label="添加附件"
              onClick={() => void pickChatAttachments()}
              disabled={!activeRoleId || sending || !bridgeReady}
            >
              <PlusIcon className="h-[14px] w-[14px] fill-current" />
            </button>
            <div className="composer-spacer flex-1" />
            <button className="send-btn grid h-[30px] w-[30px] cursor-pointer place-items-center rounded-full border-0 bg-[#1f1f1f] p-0 text-white disabled:cursor-default disabled:opacity-40" type="button" aria-label="发送消息" onClick={() => void submitMessage()} disabled={!activeRoleId || !canSubmit || sending || !bridgeReady}>
              <SendIcon className="h-[15px] w-[15px] fill-current" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
