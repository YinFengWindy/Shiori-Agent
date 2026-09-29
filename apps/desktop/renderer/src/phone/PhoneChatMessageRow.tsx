import { UserIcon } from "@phosphor-icons/react";
import { ChatFileChipContent, chatFileChipClass } from "../chat/ChatMessageAttachments";
import { ChatMessageImage } from "../chat/ChatMessageImage";
import { isChatImageAsset } from "../chat/chatImageHistory";
import { RoleAvatar } from "../roles/RoleAvatar";
import { badgeClass, cx, pressableClass, type RoleRecord } from "@shiori/plugin-sdk";
import type { PhoneChatItem } from "./phoneChatPresentation";

// Pictures stay inside the bubble column of the phone's narrow screen.
const phoneImageBounds = { width: 180, height: 220 };

const bubbleClass = "w-fit max-w-full whitespace-pre-wrap break-words rounded-md px-3 py-1.5 text-body-sm text-ink shadow-soft";

const imageButtonClass = cx(
  pressableClass,
  "block w-fit cursor-zoom-in overflow-hidden rounded-md border border-line-soft bg-surface p-0",
);

/** A message's attachments: pictures at the phone's size (a click enlarges one), other files as a plain named chip. */
function PhoneMessageMedia({ media, onOpenImage }: { media: readonly string[]; onOpenImage: (path: string) => void }) {
  return media.map((path, index) => (
    isChatImageAsset(path) ? (
      <button key={`${index}:${path}`} type="button" className={imageButtonClass} aria-label="查看大图"
        onClick={() => onOpenImage(path)}>
        <ChatMessageImage imagePath={path} bounds={phoneImageBounds} />
      </button>
    ) : (
      <span key={`${index}:${path}`} className={cx(chatFileChipClass, "max-w-full")}>
        <ChatFileChipContent path={path} />
      </span>
    )
  ));
}

/**
 * One message bubble on the phone's chat page. The role's own messages sit
 * on the right beside its avatar; everyone else's on the left beside a
 * placeholder avatar, under their name, the bound user's name with a
 * 「这是我」 badge.
 */
export function PhoneChatMessageRow({ item, role, onOpenImage }: {
  item: Extract<PhoneChatItem, { kind: "message" }>;
  role: Pick<RoleRecord, "name" | "avatar_abs">;
  /** Enlarges one of the message's pictures. */
  onOpenImage: (path: string) => void;
}) {
  const { message, side, senderLabel, isUser } = item;
  const right = side === "right";
  return (
    <li className={cx("flex min-w-0 items-start gap-2 px-3", right && "flex-row-reverse")} data-testid={`phone-message-${message.id}`} data-side={side}>
      {right ? <RoleAvatar role={role} /> : (
        <span aria-hidden="true" className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-surface-soft text-ink-muted">
          <UserIcon className="h-4 w-4" />
        </span>
      )}
      {/* No width token fits a bubble column; 78% leaves the avatar and a gutter on the phone's narrow screen. */}
      <div className={cx("grid min-w-0 max-w-[78%] gap-1", right ? "justify-items-end" : "justify-items-start")}>
        {senderLabel || isUser ? (
          <span className="flex min-w-0 max-w-full items-center gap-1 text-caption text-ink-muted">
            {senderLabel ? <span className="truncate">{senderLabel}</span> : null}
            {isUser ? <span className={cx(badgeClass, "shrink-0 px-1.5 py-0")} data-testid="phone-message-me">这是我</span> : null}
          </span>
        ) : null}
        {message.content ? (
          <p className={cx("m-0", bubbleClass, right ? "bg-accent-soft" : "bg-surface")}>{message.content}</p>
        ) : null}
        <PhoneMessageMedia media={message.media} onOpenImage={onOpenImage} />
      </div>
    </li>
  );
}
