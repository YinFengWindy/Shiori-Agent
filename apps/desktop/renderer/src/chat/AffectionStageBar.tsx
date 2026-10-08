import React from "react";
import type { AffectionDisplay } from "./affectionDisplay";

/** Shows the affection stage with a thin in-stage bar; the value and its reasons stay off the sidebar. */
export function AffectionStageBar({ affection }: { affection: AffectionDisplay }) {
  return (
    <div data-testid="chat-affection">
      <div className="flex items-center justify-between gap-3">
        <div className="text-body font-semibold text-ink-muted">好感</div>
        <div className="text-body font-semibold text-ink">{affection.stage}</div>
      </div>
      <div className="mt-1 h-1 overflow-hidden rounded-full bg-accent-soft" aria-hidden="true">
        <div
          className="h-full rounded-full bg-gradient-accent-medium transition-[width] duration-300"
          style={{ width: `${affection.percent}%` }}
        />
      </div>
    </div>
  );
}
