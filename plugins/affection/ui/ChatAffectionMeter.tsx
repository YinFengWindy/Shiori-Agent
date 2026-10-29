import type { PluginChatAffectionProps } from "@yinfengwindy/shiori-sdk";
import { resolveAffectionDisplay } from "./affectionDisplay";

/**
 * The chat sidebar's affection row: the stage name and a thin bar.
 * The numeric value stays off this surface; a malformed summary shows nothing.
 */
export function ChatAffectionMeter({ summary }: PluginChatAffectionProps) {
  const display = resolveAffectionDisplay(summary);
  if (!display) return null;
  return <div data-testid="chat-affection">
    <div className="flex items-center justify-between gap-3">
      <div className="text-body font-semibold text-ink-muted">好感</div>
      <div className="text-body font-semibold text-ink">{display.stage}</div>
    </div>
    <div className="mt-1 h-1 overflow-hidden rounded-full bg-accent-soft" aria-hidden="true">
      <div
        className="h-full rounded-full bg-gradient-accent-medium transition-[width] duration-300 motion-reduce:transition-none"
        style={{ width: `${display.percent}%` }}
      />
    </div>
  </div>;
}
