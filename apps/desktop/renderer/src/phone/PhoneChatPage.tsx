import { useMemo, useState } from "react";
import { DotsThreeIcon } from "@phosphor-icons/react";
import type { RoleRecord } from "@shiori/plugin-sdk";
import { compactIconButtonClass } from "../shared/styles";
import { phoneMemberEntryOf } from "./phoneChatInfo";
import type { PhoneConversation } from "./phoneClient";
import { phoneChatItems } from "./phoneChatPresentation";
import { PhoneChatMessageRow } from "./PhoneChatMessageRow";
import { PhoneImageLightbox } from "./PhoneImageLightbox";
import { PhoneLoadError } from "./PhoneLoadError";
import { PhoneScreenHeader } from "./PhoneScreenHeader";
import { usePhoneChatTimeline } from "./usePhoneChatTimeline";
import { usePhoneChatScroll } from "./usePhoneChatScroll";

/**
 * One conversation, read-only, as IM bubbles from the role's side, with a
 * centered time wherever the chat paused; a group's listening records
 * (kept after listening is turned off) are merged in by time. Opens at the
 * newest message, loads older ones when scrolled to the top, and takes new
 * messages live.
 * A picture opens enlarged on click. With `onOpenInfo` the header gets a
 * button to the chat info page; with `onOpenMember` the avatar of a sender
 * with a member profile entry (`phoneMemberEntryOf`) opens it.
 */
export function PhoneChatPage({ role, conversation, now, onBack, onOpenInfo, onOpenMember }: {
  role: Pick<RoleRecord, "id" | "name" | "avatar_abs">;
  conversation: PhoneConversation;
  now: Date;
  onBack: () => void;
  onOpenInfo?: () => void;
  onOpenMember?: (senderId: string) => void;
}) {
  const { messages, hasMore, error, loadOlder, retry } = usePhoneChatTimeline(role.id, conversation);
  const { viewportRef, contentRef, onScroll } = usePhoneChatScroll({ messages, hasMore, loadOlder });
  const items = useMemo(() => (messages ? phoneChatItems(messages, now) : []), [messages, now]);
  // The enlarged picture; kept after closing so the lightbox fades out with it.
  const [preview, setPreview] = useState({ imagePath: "", open: false });
  const memberOpener = (senderId: string | null) => (senderId && onOpenMember ? () => onOpenMember(senderId) : undefined);
  return (
    <div className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)]">
      <PhoneScreenHeader title={conversation.displayName} backLabel="返回会话列表" onBack={onBack} action={onOpenInfo ? (
        <button type="button" aria-label="聊天信息" data-testid="phone-chat-info" className={compactIconButtonClass} onClick={onOpenInfo}>
          <DotsThreeIcon className="h-4 w-4" aria-hidden="true" />
        </button>
      ) : null} />
      <div ref={viewportRef} className="min-h-0 overflow-y-auto" onScroll={onScroll}>
        {error ? <PhoneLoadError message={error} onRetry={retry} /> : null}
        <div ref={contentRef}>
          <ol className="m-0 grid list-none gap-2.5 p-0 py-3" aria-label={`${conversation.displayName} 聊天记录`} data-testid="phone-chat">
            {items.map((item) => (item.kind === "time" ? (
              <li key={item.key} className="justify-self-center">
                <span className="surface-glass rounded-full px-2 text-caption tabular-nums text-ink-muted">{item.label}</span>
              </li>
            ) : (
              <PhoneChatMessageRow key={item.key} item={item} role={role} onOpenImage={(imagePath) => setPreview({ imagePath, open: true })}
                onOpenMember={memberOpener(phoneMemberEntryOf(item, conversation))} />
            )))}
          </ol>
        </div>
      </div>
      <PhoneImageLightbox imagePath={preview.imagePath} open={preview.open}
        onClose={() => setPreview((current) => ({ ...current, open: false }))} />
    </div>
  );
}
