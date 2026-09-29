import { CaretLeftIcon, ChatCircleIcon, UserIcon, UsersThreeIcon } from "@phosphor-icons/react";
import { formatChatListTime } from "../roles/roleChatPreview";
import { emptyStateLines } from "../shared/mascot/mascotLines";
import { compactIconButtonClass } from "../shared/styles";
import type { PhoneChatType, PhoneConversation } from "./phoneClient";
import { PhoneEmptyState } from "./PhoneEmptyState";
import { PhoneLoadError } from "./PhoneLoadError";
import { phoneConversationPreview, type PhoneApp } from "./phonePresentation";

/** Group or private mark; a conversation whose type no message recorded gets a neutral one rather than a guess. */
function ChatTypeMark({ chatType }: { chatType: PhoneChatType | null }) {
  if (chatType === "group") return <UsersThreeIcon className="h-5 w-5" />;
  if (chatType === "private") return <UserIcon className="h-5 w-5" />;
  return <ChatCircleIcon className="h-5 w-5" />;
}

function ConversationRow({ conversation, now }: { conversation: PhoneConversation; now: Date }) {
  return (
    <li className="flex min-w-0 items-center gap-2.5 px-3 py-2" data-testid={`phone-conversation-${conversation.threadId}`}>
      <span aria-hidden="true" className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-accent-soft text-accent-text">
        <ChatTypeMark chatType={conversation.chatType} />
      </span>
      <span className="grid min-w-0 flex-1 gap-0.5">
        <span className="flex min-w-0 items-baseline gap-2">
          <span className="min-w-0 truncate text-body-sm font-semibold text-ink">{conversation.displayName}</span>
          <span className="ml-auto shrink-0 text-caption tabular-nums text-ink-muted">
            {formatChatListTime(conversation.lastMessage.timestamp, now)}
          </span>
        </span>
        <span className="truncate text-caption text-ink-muted">{phoneConversationPreview(conversation)}</span>
      </span>
    </li>
  );
}

/**
 * One app's conversation list, newest message first, under a header with a
 * back button to the home screen. Rows only show for now; opening a
 * conversation is the phone chat page (#485).
 */
export function PhoneConversationList({ app, conversations, error, now, onRetry, onBack }: {
  app: PhoneApp;
  /** This account's conversations; null while they load. */
  conversations: PhoneConversation[] | null;
  error: string;
  now: Date;
  onRetry: () => void;
  onBack: () => void;
}) {
  return (
    <div className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)]">
      <header className="surface-glass flex min-w-0 items-center gap-1 px-2 py-1.5">
        <button type="button" aria-label="返回主屏" data-testid="phone-back" onClick={onBack} className={compactIconButtonClass}>
          <CaretLeftIcon className="h-4 w-4" aria-hidden="true" />
        </button>
        <h3 className="m-0 min-w-0 truncate text-body font-semibold text-ink">{app.label}</h3>
      </header>
      <div className="min-h-0 overflow-y-auto">
        {error ? (
          <PhoneLoadError message={error} onRetry={onRetry} />
        ) : !conversations ? null : conversations.length ? (
          <ul className="surface-glass m-0 grid list-none p-0" aria-label={`${app.label} 会话`} data-testid="phone-conversations">
            {conversations.map((conversation) => <ConversationRow key={conversation.threadId} conversation={conversation} now={now} />)}
          </ul>
        ) : (
          <PhoneEmptyState line={emptyStateLines.phoneNoConversations} label="还没有会话" testId="phone-conversations-empty" />
        )}
      </div>
    </div>
  );
}
