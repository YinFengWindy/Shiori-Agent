import { CaretDown } from "@phosphor-icons/react";
import { useId, type ReactNode } from "react";
import { cx, sidebarNavItemClass } from "@shiori/sdk";

type CollapsibleFieldProps = {
  title: string;
  /** Current draft text, shown as a compact preview while the editor is closed. */
  value: string;
  expanded: boolean;
  onToggle: () => void;
  children: ReactNode;
};

/** A transparent, controlled field disclosure with an accessible heading and draft preview. */
export function CollapsibleField({ title, value, expanded, onToggle, children }: CollapsibleFieldProps) {
  const id = useId();
  const titleId = `${id}-title`;
  const bodyId = `${id}-body`;
  const preview = value.trim().replace(/\s+/g, " ");
  const summary = preview.length > 160 ? `${preview.slice(0, 160)}…` : preview || "未填写";

  return (
    <section className="min-w-0 border-t border-line-soft py-4 first:border-t-0 first:pt-0 last:pb-0">
      <h2 className="m-0">
        <button
          type="button"
          className={cx(sidebarNavItemClass, "flex min-h-11 w-full items-center justify-between gap-4 px-2 py-2 text-left text-title-sm text-ink")}
          aria-expanded={expanded}
          aria-controls={bodyId}
          onClick={onToggle}
        >
          <span id={titleId}>{title}</span>
          <CaretDown className={cx("h-4 w-4 shrink-0 text-ink-muted", expanded && "rotate-180")} aria-hidden="true" />
        </button>
      </h2>
      {expanded ? null : <p className="m-0 mt-1 line-clamp-2 break-words px-2 text-body text-ink-muted">{summary}</p>}
      {/* Unmount the editor so closed fields cannot scroll or receive focus; the caller owns the draft. */}
      <div id={bodyId} role="region" aria-labelledby={titleId} hidden={!expanded}>
        {expanded ? <div className="pt-3">{children}</div> : null}
      </div>
    </section>
  );
}
