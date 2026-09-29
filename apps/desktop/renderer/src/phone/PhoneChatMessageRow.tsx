import { UserIcon } from "@phosphor-icons/react";
import { ChatMessageImage } from "../chat/ChatMessageImage";
import { getChatAttachmentName } from "../chat/chatMessageActions";
import { isChatImageAsset } from "../chat/chatImageHistory";
import { RoleAvatar } from "../roles/RoleAvatar";
import { toFileUrl } from "../shared/format";
import { DocumentIcon } from "../shared/icons";
import { badgeClass, cx } from "../shared/styles";
import type { RoleRecord } from "../shared/types";
import type { PhoneChatItem } from "./phoneChatPresentation";

// Pictures stay inside the bubble column of the phone's narrow screen.
const phoneImageBounds = { width: 180, height: 220 };

const bubbleClass = "w-fit max-w-full whitespace-pre-wrap break-words rounded-md px-3 py-1.5 text-body-sm text-ink shadow-soft";

/** A message's attachments: pictures at the phone's size, other files as a named chip. */
function PhoneMessageMedia({ media }: { media: readonly string[] }) {
  return media.map((path, index) => (
    isChatImageAsset(path) ? (
      <span key={`${index}:${path}`} className="block w-fit overflow-hidden rounded-md border border-line-soft bg-surface">
        <ChatMessageImage imagePath={path} bounds={phoneImageBounds} />
      </span>
    ) : (
      <a key={`${index}:${path}`} href={toFileUrl(path)} target="_blank" rel="noreferrer"
        className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-line-soft bg-surface px-2.5 py-1 text-caption text-ink">
        <DocumentIcon className="h-3 w-3 shrink-0 stroke-current" />
        <span className="truncate">{getChatAttachmentName(path)}</span>
      </a>
    )
  ));
}

/**
 * One message bubble on the phone's chat page. The role's own messages sit
 * on the right beside its avatar; everyone else's on the left beside a
 * placeholder avatar, under their name, the bound user's name with a
 * 「这是我」 badge.
 */
export function PhoneChatMessageRow({ item, role }: {
  item: Extract<PhoneChatItem, { kind: "message" }>;
  role: Pick<RoleRecord, "name" | "avatar_abs">;
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
        <PhoneMessageMedia media={message.media} />
      </div>
    </li>
  );
}
