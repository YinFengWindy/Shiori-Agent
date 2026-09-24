import { CaretRight } from "@phosphor-icons/react";
import type { ReactNode } from "react";
import { cx } from "../shared/styles";

/**
 * Collapsible body for settings disclosures, animated by the
 * `.disclosure-content` 0fr → 1fr rule in styles.css. The content stays
 * mounted (a toggle inside keeps its state) but is `inert` while closed, so
 * it is out of the tab order and hidden from assistive tech.
 */
export function SettingsDisclosure({ open, id, children }: { open: boolean; id?: string; children: ReactNode }) {
  return (
    <div id={id} className={cx("disclosure-content", open && "disclosure-content-open")}>
      <div inert={!open}>{children}</div>
    </div>
  );
}

/** The caret header that opens and closes a `SettingsDisclosure` (pass the body's id as `controls`). */
export function SettingsDisclosureToggle({ open, controls, onToggle, children }: {
  open: boolean;
  controls: string;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      className="-mx-1 flex w-fit items-center gap-2 rounded-md px-1 py-0.5 text-left text-body-sm font-semibold text-ink-secondary hover:bg-surface-hover"
      aria-expanded={open}
      aria-controls={controls}
      onClick={onToggle}
    >
      <CaretRight className={cx("h-3.5 w-3.5 text-ink-muted transition-transform duration-quick ease-out-soft", open && "rotate-90")} weight="bold" aria-hidden="true" />
      {children}
    </button>
  );
}
