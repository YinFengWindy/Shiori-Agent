import { useEffect, useRef, type KeyboardEvent, type MouseEvent } from "react";
import { X } from "@phosphor-icons/react";
import type { AdvBacklogEntry } from "../../adv/advModel";
import { SITE_ADV_COPY } from "../../content/siteCopy";
import { useDialogFocus } from "../../hooks/useDialogFocus";

interface AdvBacklogProps {
  speaker: string;
  entries: readonly AdvBacklogEntry[];
  onClose: () => void;
}

/**
 * Backlog (文本记录) dialog: every line spoken so far plus the choices the
 * visitor picked, scrolled to the latest entry. Esc and right-click close
 * the backlog only — they are stopped here so the screen-level handlers in
 * `useSiteScreen` don't also send the visitor back to the title.
 */
export function AdvBacklog({ speaker, entries, onClose }: AdvBacklogProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLOListElement>(null);
  useDialogFocus(dialogRef);

  useEffect(() => {
    const list = listRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, []);

  function handleKeyDown(event: KeyboardEvent) {
    if (event.key !== "Escape") return;
    event.stopPropagation();
    onClose();
  }

  function handleContextMenu(event: MouseEvent) {
    event.preventDefault();
    event.stopPropagation();
    onClose();
  }

  return (
    <div className="site-modal-backdrop fixed inset-0 z-50 grid place-items-center p-4" onClick={onClose} onContextMenu={handleContextMenu}>
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="site-adv-backlog-title"
        onKeyDown={handleKeyDown}
        onClick={(event) => event.stopPropagation()}
        className="site-panel site-adv-backlog flex w-full max-w-2xl flex-col rounded-xl"
      >
        <div className="flex items-center justify-between gap-4 px-6 pb-3 pt-5">
          <h2 id="site-adv-backlog-title" className="font-display text-title text-site-ink">
            {SITE_ADV_COPY.backlogTitle}
          </h2>
          <button type="button" onClick={onClose} aria-label={SITE_ADV_COPY.backlogClose} className="site-icon-button rounded-md p-1.5">
            <X size={16} aria-hidden="true" />
          </button>
        </div>
        <ol ref={listRef} tabIndex={0} aria-label={SITE_ADV_COPY.backlogTitle} className="site-adv-backlog-list min-h-0 flex-1 overflow-y-auto px-6 pb-6">
          {entries.map((entry, index) =>
            entry.kind === "line" ? (
              <li key={index} className="site-adv-backlog-line">
                <span className="site-adv-backlog-speaker font-display">{speaker}</span>
                <p className="text-body text-site-ink">{entry.text}</p>
              </li>
            ) : (
              <li key={index} className="site-adv-backlog-choice text-body-sm">
                {SITE_ADV_COPY.backlogChoice}「{entry.label}」
              </li>
            ),
          )}
        </ol>
      </div>
    </div>
  );
}
