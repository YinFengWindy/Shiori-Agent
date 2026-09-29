import { PuzzlePieceIcon } from "@phosphor-icons/react";
import { InlineError } from "../shared/feedback/InlineError";
import { emptyStateLines } from "../shared/mascot/mascotLines";
import { compactGhostButtonClass, cx, pressableClass } from "../shared/styles";
import { PhoneEmptyState } from "./PhoneEmptyState";
import type { PhoneApp } from "./phonePresentation";

const appButtonClass = cx(
  pressableClass,
  "grid w-full min-w-0 cursor-pointer justify-items-center gap-1 rounded-md p-1 hover:bg-surface-hover",
);

/**
 * The home screen: one app per account of the role. An offline account
 * still has its app, dimmed and marked 「离线」 under its icon.
 */
export function PhoneHomeScreen({ apps, error, onRetry, onOpen }: {
  /** Null while the accounts load. */
  apps: PhoneApp[] | null;
  error: string;
  onRetry: () => void;
  onOpen: (accountId: string) => void;
}) {
  if (error) {
    return <div className="p-3">
      <InlineError message={error} actions={<button type="button" className={compactGhostButtonClass} onClick={onRetry}>重试</button>} />
    </div>;
  }
  if (!apps) return null;
  if (!apps.length) {
    return <PhoneEmptyState line={emptyStateLines.phoneNoAccounts} label="还没有账号" testId="phone-home-empty" />;
  }
  return (
    <ul className="m-0 grid list-none grid-cols-3 content-start gap-x-2 gap-y-4 px-4 pt-5" aria-label="应用" data-testid="phone-home">
      {apps.map(({ accountId, label, Icon = PuzzlePieceIcon, offline }) => (
        <li key={accountId} className="min-w-0">
          <button type="button" className={appButtonClass} aria-label={offline ? `${label}，离线` : label}
            data-testid={`phone-app-${accountId}`} onClick={() => onOpen(accountId)}>
            <span className={cx(
              "relative grid h-14 w-14 place-items-center rounded-md bg-surface text-ink-secondary shadow-soft",
              offline && "opacity-60",
            )}>
              <Icon className="h-7 w-7" />
            </span>
            <span className="phone-glass max-w-full truncate rounded-full px-1.5 text-caption text-ink">{label}</span>
            {offline ? <span className="rounded-full bg-surface-soft px-1.5 text-caption text-ink-muted">离线</span> : null}
          </button>
        </li>
      ))}
    </ul>
  );
}
