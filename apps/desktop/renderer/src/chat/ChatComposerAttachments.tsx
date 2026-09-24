import { isChatImageAsset } from "./chatImageHistory";
import { getChatAttachmentName } from "./chatMessageActions";
import { DeleteIcon, DocumentIcon } from "../shared/icons";
import { toFileUrl } from "../shared/format";

type ChatComposerAttachmentsProps = {
  paths: string[];
  disabled: boolean;
  /** Past this height the strip scrolls instead of pushing the composer up. */
  maxHeight: number;
  onRemove: (path: string) => void;
};

function getAttachmentExtensionLabel(path: string): string {
  const attachmentName = getChatAttachmentName(path);
  const dotIndex = attachmentName.lastIndexOf(".");
  if (dotIndex < 0 || dotIndex === attachmentName.length - 1) {
    return "FILE";
  }
  return attachmentName.slice(dotIndex + 1).toUpperCase();
}

/** Pending attachments above the composer text: image thumbnails and file chips, each removable. */
export function ChatComposerAttachments({ paths, disabled, maxHeight, onRemove }: ChatComposerAttachmentsProps) {
  if (!paths.length) return null;
  return (
    <div
      className="scrollbar-soft flex flex-wrap gap-2 overflow-y-auto"
      style={{ maxHeight }}
      data-testid="composer-attachments"
    >
      {paths.map((path) => (
        isChatImageAsset(path) ? (
          <span
            key={path}
            className="relative h-14 w-14 flex-none overflow-hidden rounded-md border border-line-soft bg-surface-soft"
          >
            <img
              className="h-full w-full object-cover"
              src={toFileUrl(path)}
              alt=""
            />
            <button
              className="absolute right-1 top-1 grid h-4 w-4 place-items-center rounded-full bg-white/90 p-0 text-ink-faint shadow-soft transition hover:text-ink focus:outline-none disabled:cursor-default disabled:opacity-40"
              type="button"
              aria-label="移除图片附件"
              onClick={() => onRemove(path)}
              disabled={disabled}
            >
              <DeleteIcon className="h-[10px] w-[10px] fill-current" />
            </button>
          </span>
        ) : (
          <span
            key={path}
            className="relative inline-flex max-w-[220px] items-center gap-2 rounded-md border border-line-soft bg-surface-soft px-3 py-2 text-left text-ink-secondary"
          >
            <span className="grid h-9 w-9 flex-none place-items-center rounded-md border border-line-soft bg-white text-ink-muted">
              <DocumentIcon className="h-4 w-4 stroke-current" />
            </span>
            <span className="min-w-0 flex-1 pr-4">
              <span className="block truncate text-[12px] font-medium leading-[1.2] text-ink">
                {getChatAttachmentName(path)}
              </span>
              <span className="mt-1 block text-[11px] leading-none text-ink-faint">
                {getAttachmentExtensionLabel(path)}
              </span>
            </span>
            <button
              className="absolute right-2 top-2 grid h-4 w-4 place-items-center rounded-full border-0 bg-transparent p-0 text-ink-faint transition hover:text-ink focus:outline-none disabled:cursor-default disabled:opacity-40"
              type="button"
              aria-label={`移除附件 ${getChatAttachmentName(path)}`}
              onClick={() => onRemove(path)}
              disabled={disabled}
            >
              <DeleteIcon className="h-[10px] w-[10px] fill-current" />
            </button>
          </span>
        )
      ))}
    </div>
  );
}
