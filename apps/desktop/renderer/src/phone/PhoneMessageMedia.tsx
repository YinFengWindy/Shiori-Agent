import { ChatFileChipContent, chatFileChipClass } from "../chat/ChatMessageAttachments";
import { ChatMessageImage } from "../chat/ChatMessageImage";
import { isChatImageAsset } from "../chat/chatImageHistory";
import { cx, pressableClass } from "@shiori/plugin-sdk";

/** Pictures stay inside the bubble column of the phone's narrow screen. */
export const phoneImageBounds = { width: 180, height: 220 };

const imageButtonClass = cx(
  pressableClass,
  "block w-fit cursor-zoom-in overflow-hidden rounded-md border border-line-soft bg-surface p-0",
);

/** A message's attachments: pictures within `bounds` (a click enlarges one), other files as a plain named chip. */
export function PhoneMessageMedia({ media, bounds = phoneImageBounds, onOpenImage }: {
  media: readonly string[];
  bounds?: { width: number; height: number };
  onOpenImage: (path: string) => void;
}) {
  return media.map((path, index) => (
    isChatImageAsset(path) ? (
      <button key={`${index}:${path}`} type="button" className={imageButtonClass} aria-label="查看大图"
        onClick={() => onOpenImage(path)}>
        <ChatMessageImage imagePath={path} bounds={bounds} />
      </button>
    ) : (
      <span key={`${index}:${path}`} className={cx(chatFileChipClass, "max-w-full")}>
        <ChatFileChipContent path={path} />
      </span>
    )
  ));
}
