import type React from "react";
import { ChatMessageImage } from "./ChatMessageImage";
import { getChatAttachmentName } from "./chatMessageActions";
import { buildChatImageHistoryKey, isChatImageAsset } from "./chatImageHistory";
import { normalizeSessionMediaPaths } from "./chatMedia";
import { toFileUrl } from "../shared/format";
import { DocumentIcon } from "../shared/icons";

type ChatMessageAttachmentsProps = {
  messageKey: string;
  media: unknown;
  onBeginAttachmentDrag: (path: string) => void;
  onOpenImagePreview: (historyKey: string) => void;
};

/** Renders media outside the text bubble so attachments retain their own interaction surface. */
export function ChatMessageAttachments({
  messageKey,
  media,
  onBeginAttachmentDrag,
  onOpenImagePreview,
}: ChatMessageAttachmentsProps) {
  const paths = normalizeSessionMediaPaths(media);
  if (!paths.length) return null;

  function handleAttachmentDragStart(event: React.DragEvent<HTMLElement>, path: string): void {
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.effectAllowed = "copy";
    onBeginAttachmentDrag(path);
  }

  return (
    <div className="mt-2 grid gap-2" data-message-media="separate">
      {paths.map((item, mediaIndex) => (
        isChatImageAsset(item) ? (
          <button
            key={`${messageKey}:${mediaIndex}:${item}`}
            className="block w-fit max-w-full cursor-grab overflow-hidden rounded-[12px] border border-black/8 bg-white/70 p-0 text-left transition hover:bg-white active:cursor-grabbing focus:outline-none"
            type="button"
            draggable
            onDragStart={(event) => handleAttachmentDragStart(event, item)}
            onClick={() => onOpenImagePreview(buildChatImageHistoryKey(messageKey, mediaIndex))}
          >
            <ChatMessageImage imagePath={item} />
          </button>
        ) : (
          <a
            key={`${messageKey}:${mediaIndex}:${item}`}
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
            <span className="truncate font-medium">{getChatAttachmentName(item)}</span>
          </a>
        )
      ))}
    </div>
  );
}
