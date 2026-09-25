import { CaretDown } from "@phosphor-icons/react";
import { cx } from "../styles";

/**
 * The 「详情」 fold shared by toasts and inline errors: a small toggle and,
 * once opened, the technical cause in a scrollable monospace block. Open
 * state is the caller's, since a toast holds its timer while it is open.
 */
export function FeedbackDetail({ detail, open, onToggle }: { detail: string; open: boolean; onToggle: () => void }) {
  return (
    <>
      <button
        type="button"
        className="inline-flex w-fit items-center gap-1 rounded-md text-caption font-medium text-ink-muted transition-colors hover:text-ink"
        aria-expanded={open}
        onClick={onToggle}
      >
        详情
        <CaretDown className={cx("h-3 w-3 transition-transform duration-quick", open && "rotate-180")} weight="bold" aria-hidden="true" />
      </button>
      {open ? (
        <pre className="scrollbar-stable m-0 max-h-32 overflow-auto whitespace-pre-wrap break-words rounded-md bg-white/60 p-2 text-left font-mono text-caption text-ink-secondary">{detail}</pre>
      ) : null}
    </>
  );
}
