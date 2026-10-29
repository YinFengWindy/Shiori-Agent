/**
 * The chat sidebar's affection row: the stage name and a thin bar.
 * The numeric value stays off this surface.
 */
export function ChatAffectionMeter({ stage, percent }: { stage: string; percent: number }) {
  return <div data-testid="chat-affection">
    <div className="flex items-center justify-between gap-3">
      <div className="text-body font-semibold text-ink-muted">好感</div>
      <div className="text-body font-semibold text-ink">{stage}</div>
    </div>
    <div className="mt-1 h-1 overflow-hidden rounded-full bg-accent-soft" aria-hidden="true">
      <div
        className="h-full rounded-full bg-gradient-accent-medium transition-[width] duration-300 motion-reduce:transition-none"
        style={{ width: `${percent}%` }}
      />
    </div>
  </div>;
}
