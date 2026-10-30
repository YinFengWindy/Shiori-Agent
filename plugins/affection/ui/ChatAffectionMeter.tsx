import type { AffectionSummary } from "@yinfengwindy/shiori-sdk";
import { resolveAffectionDisplay } from "./affectionDisplay";
import { StatusMeter } from "./StatusMeter";

/**
 * The chat sidebar's affection row: the stage name and a thin bar.
 * The numeric value stays off this surface; a malformed summary shows nothing.
 */
export function ChatAffectionMeter({ summary }: { summary: AffectionSummary }) {
  const display = resolveAffectionDisplay(summary);
  if (!display) return null;
  return <StatusMeter label="好感" value={display.stage} percent={display.percent} heightClass="h-1" testId="chat-affection" />;
}
