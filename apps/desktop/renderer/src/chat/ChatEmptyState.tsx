import { toFileUrl } from "../shared/format";
import { cx, pressableClass } from "../shared/styles";
import type { RoleRecord } from "../shared/types";

/** Openers offered on an empty chat: the chip label and the text it puts in the composer (never sent automatically). */
export const chatEmptyStateSuggestions = [
  { label: "打个招呼", text: "你好呀～" },
  { label: "聊聊今天", text: "今天过得怎么样？" },
  { label: "你是谁？", text: "你是谁？" },
] as const;

type ChatEmptyStateProps = {
  role: RoleRecord;
  onPickSuggestion: (text: string) => void;
};

/** The first screen of a role's (single, lifelong) conversation: who is here, and a few ways to begin. */
export function ChatEmptyState({ role, onPickSuggestion }: ChatEmptyStateProps) {
  return (
    <div className="chat-empty-state motion-fade-enter pointer-events-none absolute inset-x-0 top-0 z-[1] grid justify-items-center gap-3 px-6 pt-[18vh] text-center" data-testid="chat-empty-state">
      {role.avatar_abs ? (
        <img className="h-20 w-20 rounded-full border-2 border-white object-cover shadow-soft" src={toFileUrl(role.avatar_abs)} alt={`${role.name} 的头像`} />
      ) : (
        <span className="grid h-20 w-20 place-items-center rounded-full border-2 border-white bg-accent-softer font-display text-headline text-accent-text shadow-soft">
          {role.name.slice(0, 1).toUpperCase()}
        </span>
      )}
      <div className="font-display text-title text-ink">{role.name}</div>
      {role.description ? <div className="max-w-[420px] text-body-sm text-ink-muted">{role.description}</div> : null}
      <div className="pointer-events-auto mt-2 flex flex-wrap justify-center gap-2">
        {chatEmptyStateSuggestions.map((suggestion) => (
          <button
            key={suggestion.label}
            className={cx(
              pressableClass,
              "surface-glass h-8 rounded-full px-3.5 text-body-sm text-ink-secondary hover:bg-white hover:text-ink",
            )}
            type="button"
            onClick={() => onPickSuggestion(suggestion.text)}
          >
            {suggestion.label}
          </button>
        ))}
      </div>
    </div>
  );
}
