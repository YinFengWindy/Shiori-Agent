import type React from "react";
import { cx } from "../shared/styles";

/**
 * The floating glass card that holds one step's form over the scene. Only
 * the body scrolls; the footer (primary action) is always in view, whatever
 * the window height. Enters like other overlays (`motion-dialog-enter`).
 */
export function OnboardingCard({ title, headerAction, footer, error, children, onSubmit }: {
  /** Card heading; a card that presents its own heading in the body omits it. */
  title?: React.ReactNode;
  /** Secondary control beside the title (e.g. role card import). */
  headerAction?: React.ReactNode;
  footer: React.ReactNode;
  /** Inline failure for the card's action, pinned above the footer so it is never scrolled away. */
  error?: string;
  children: React.ReactNode;
  /** When set, the card is a form and Enter submits it. */
  onSubmit?: () => void;
}) {
  const content = (
    <>
      {title ? (
        <header className="flex shrink-0 items-center justify-between gap-3 px-5 pb-2 pt-4">
          <h2 className="m-0 min-w-0 truncate font-display text-title text-ink">{title}</h2>
          {headerAction}
        </header>
      ) : null}
      <div className={cx("scrollbar-stable min-h-0 flex-1 overflow-y-auto px-5", !title && "pt-5")}>{children}</div>
      {error ? <p role="alert" className="m-0 shrink-0 break-words border-t border-line-soft bg-danger-soft/60 px-5 py-2 text-body-sm text-danger-text">{error}</p> : null}
      <footer className="flex shrink-0 flex-wrap items-center justify-end gap-3 border-t border-line-soft px-5 py-3">{footer}</footer>
    </>
  );
  const className = "onboarding-card surface-glass-strong motion-dialog-enter pointer-events-auto flex max-h-full min-h-0 w-full flex-col rounded-xl";
  return onSubmit ? (
    <form className={className} onSubmit={(event) => { event.preventDefault(); onSubmit(); }}>{content}</form>
  ) : (
    <section className={className}>{content}</section>
  );
}
