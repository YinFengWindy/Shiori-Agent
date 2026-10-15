import type { Icon } from "@phosphor-icons/react";

/** A centered glyph and one short fact, for an empty list or an empty pane. */
export function EmptyState({ icon: Glyph, label }: { icon: Icon; label: string }) {
  return (
    <div className="grid justify-items-center gap-3 px-2 py-10 text-center">
      <span className="grid h-11 w-11 place-items-center rounded-full bg-accent-softer text-accent">
        <Glyph className="h-5 w-5" aria-hidden="true" />
      </span>
      <span className="text-body-sm text-ink-muted">{label}</span>
    </div>
  );
}
