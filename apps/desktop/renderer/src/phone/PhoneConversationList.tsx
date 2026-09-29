import { ChatCircleIcon, UserIcon, UsersThreeIcon } from "@phosphor-icons/react";
import { formatChatListTime } from "../roles/roleChatPreview";
import { emptyStateLines } from "../shared/mascot/mascotLines";
import { cx, pressableClass } from "../shared/styles";
import type { PhoneChatType, PhoneConversation } from "./phoneClient";
import { PhoneEmptyState } from "./PhoneEmptyState";
import { PhoneLoadError } from "./PhoneLoadError";
import { phoneConversationPreview, type PhoneApp } from "./phonePresentation";
import { PhoneScreenHeader } from "./PhoneScreenHeader";

const rowButtonClass = cx(
  pressableClass,
  "flex w-full min-w-0 cursor-pointer items-center gap-2.5 px-3 py-2 text-left hover:bg-surface-hover",
);

/** Group or private mark; a conversation whose type no message recorded gets a neutral one rather than a guess. */
function ChatTypeMark({ chatType }: { chatType: PhoneChatType | null }) {
  if (chatType === "group") return <UsersThreeIcon className="h-5 w-5" />;
  if (chatType === "private") return <UserIcon className="h-5 w-5" />;
  return <ChatCircleIcon className="h-5 w-5" />;
}

function ConversationRow({ conversation, now, onOpen }: {
  conversation: PhoneConversation;
  now: Date;
  onOpen: (threadId: string) => void;
}) {
  return (
    <li className="min-w-0">
      <button type="button" className={rowButtonClass} data-testid={`phone-conversation-${conversation.threadId}`}
        onClick={() => onOpen(conversation.threadId)}>
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
      </button>
    </li>
  );
}

/**
 * One app's conversation list, newest message first, under a header with a
 * back button to the home screen. Tapping a row opens its chat page.
 */
export function PhoneConversationList({ app, conversations, error, now, onRetry, onBack, onOpen }: {
  app: PhoneApp;
  /** This account's conversations; null while they load. */
  conversations: PhoneConversation[] | null;
  error: string;
  now: Date;
  onRetry: () => void;
  onBack: () => void;
  onOpen: (threadId: string) => void;
}) {
  return (
    <div className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)]">
      <PhoneScreenHeader title={app.label} backLabel="返回主屏" onBack={onBack} />
      <div className="min-h-0 overflow-y-auto">
        {error ? (
          <PhoneLoadError message={error} onRetry={onRetry} />
        ) : !conversations ? null : conversations.length ? (
          <ul className="surface-glass m-0 grid list-none p-0" aria-label={`${app.label} 会话`} data-testid="phone-conversations">
            {conversations.map((conversation) => <ConversationRow key={conversation.threadId} conversation={conversation} now={now} onOpen={onOpen} />)}
          </ul>
        ) : (
          <PhoneEmptyState line={emptyStateLines.phoneNoConversations} label="还没有会话" testId="phone-conversations-empty" />
        )}
      </div>
    </div>
  );
}
