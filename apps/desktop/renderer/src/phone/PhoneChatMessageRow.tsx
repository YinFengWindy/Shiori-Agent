import { EarIcon, UserIcon } from "@phosphor-icons/react";
import { ChatFileChipContent, chatFileChipClass } from "../chat/ChatMessageAttachments";
import { ChatMessageImage } from "../chat/ChatMessageImage";
import { isChatImageAsset } from "../chat/chatImageHistory";
import { RoleAvatar } from "../roles/RoleAvatar";
import { badgeClass, cx, pressableClass, type RoleRecord } from "@shiori/plugin-sdk";
import { PhoneAvatarFace } from "./PhoneAvatarFace";
import type { PhoneChatItem } from "./phoneChatPresentation";

// Pictures stay inside the bubble column of the phone's narrow screen.
const phoneImageBounds = { width: 180, height: 220 };

const bubbleClass = "w-fit max-w-full whitespace-pre-wrap break-words rounded-md px-3 py-1.5 text-body-sm";

/** A bubble's surface: the role's own, someone's said in the conversation, or one heard while listening in (quieter, dashed). */
const bubbleSurfaceClass = {
  right: "bg-accent-soft text-ink shadow-soft",
  left: "bg-surface text-ink shadow-soft",
  listened: "border border-dashed border-line bg-surface-soft text-ink-secondary",
};

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

const otherAvatarClass = "grid h-8 w-8 shrink-0 place-items-center overflow-hidden rounded-full bg-surface-soft text-ink-muted";

const placeholder = <UserIcon className="h-4 w-4" aria-hidden="true" />;

/** Someone else's avatar; a button opening their member profile when `onOpen` is given. */
function OtherAvatar({ label, avatarPath, onOpen }: { label: string | null; avatarPath: string | null; onOpen?: () => void }) {
  if (!onOpen) {
    return <span aria-hidden="true" className={otherAvatarClass}><PhoneAvatarFace avatarPath={avatarPath} placeholder={placeholder} /></span>;
  }
  return (
    <button type="button" className={cx(pressableClass, otherAvatarClass, "cursor-pointer border-0 p-0 hover:text-ink")}
      aria-label={`${label ?? "成员"} 的档案`} data-testid="phone-member-avatar" onClick={onOpen}>
      <PhoneAvatarFace avatarPath={avatarPath} placeholder={placeholder} />
    </button>
  );
}

/**
 * One message bubble on the phone's chat page. The role's own messages sit
 * on the right beside its avatar; everyone else's on the left beside their
 * cached platform avatar (a placeholder without one), under their name, the
 * bound user's name with a 「这是我」 badge. A message heard while listening
 * in on the group has a quieter, dashed bubble and an ear mark by the name.
 * The members a group message @s lead its text as 「@名字」.
 * `onOpenMember`, when given, makes that avatar open the sender's member
 * profile.
 */
export function PhoneChatMessageRow({ item, role, onOpenImage, onOpenMember }: {
  item: Extract<PhoneChatItem, { kind: "message" }>;
  role: Pick<RoleRecord, "name" | "avatar_abs">;
  /** Enlarges one of the message's pictures. */
  onOpenImage: (path: string) => void;
  onOpenMember?: () => void;
}) {
  const { message, side, senderLabel, isUser, mentionLabels } = item;
  const right = side === "right";
  const surface = message.listened ? "listened" : side;
  return (
    <li className={cx("flex min-w-0 items-start gap-2 px-3", right && "flex-row-reverse")} data-testid={`phone-message-${message.id}`}
      data-side={side} data-listened={message.listened || undefined}>
      {right ? <RoleAvatar role={role} /> : <OtherAvatar label={senderLabel} avatarPath={message.senderAvatarPath} onOpen={onOpenMember} />}
      {/* No width token fits a bubble column; 78% leaves the avatar and a gutter on the phone's narrow screen. */}
      <div className={cx("grid min-w-0 max-w-[78%] gap-1", right ? "justify-items-end" : "justify-items-start")}>
        {senderLabel || isUser || message.listened ? (
          <span className="flex min-w-0 max-w-full items-center gap-1 text-caption text-ink-muted">
            {message.listened ? <EarIcon className="h-3 w-3 shrink-0" role="img" aria-label="旁听" /> : null}
            {senderLabel ? <span className="truncate">{senderLabel}</span> : null}
            {isUser ? <span className={cx(badgeClass, "shrink-0 px-1.5 py-0")} data-testid="phone-message-me">这是我</span> : null}
          </span>
        ) : null}
        {message.content || mentionLabels.length ? (
          <p className={cx("m-0", bubbleClass, bubbleSurfaceClass[surface])}>
            {mentionLabels.length ? <span className="text-accent-text">{`${mentionLabels.join(" ")} `}</span> : null}
            {message.content}
          </p>
        ) : null}
        <PhoneMessageMedia media={message.media} onOpenImage={onOpenImage} />
      </div>
    </li>
  );
}
