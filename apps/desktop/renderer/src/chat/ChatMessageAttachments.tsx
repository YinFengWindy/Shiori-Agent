import type React from "react";
import { ChatMessageImage } from "./ChatMessageImage";
import { getChatAttachmentName } from "./chatMessageActions";
import { buildChatImageHistoryKey, isChatImageAsset } from "./chatImageHistory";
import { normalizeSessionMediaPaths } from "./chatMedia";
import { toFileUrl } from "../shared/format";
import { DocumentIcon } from "../shared/icons";
import { cx } from "@shiori/sdk";

/** A file attachment's pill (without its width cap or interaction), shared with the phone's read-only chat. */
export const chatFileChipClass =
  "inline-flex items-center gap-2.5 rounded-full border border-line-soft bg-surface-soft px-3 py-2 text-[12px] text-ink";

/** Inside a file attachment's pill: the document mark and the file name. */
export function ChatFileChipContent({ path }: { path: string }) {
  return (
    <>
      <span className="grid h-6 w-6 flex-none place-items-center rounded-full bg-transparent text-ink-faint">
        <DocumentIcon className="h-[13px] w-[13px] stroke-current" />
      </span>
      <span className="truncate font-medium">{getChatAttachmentName(path)}</span>
    </>
  );
}

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
            className="block w-fit max-w-full cursor-grab overflow-hidden rounded-md border border-line-soft bg-white/70 p-0 text-left transition hover:bg-white active:cursor-grabbing focus:outline-none"
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
            className={cx(chatFileChipClass, "max-w-[280px] cursor-grab transition hover:bg-white active:cursor-grabbing focus:outline-none")}
            draggable
            onDragStart={(event) => handleAttachmentDragStart(event, item)}
          >
            <ChatFileChipContent path={item} />
          </a>
        )
      ))}
    </div>
  );
}
