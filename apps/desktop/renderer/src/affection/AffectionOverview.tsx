import { LockSimpleIcon } from "@phosphor-icons/react";
import type { AffectionSummary } from "@yinfengwindy/shiori-sdk";
import { cx } from "@yinfengwindy/shiori-sdk";
import { affectionMax, affectionMin } from "./affectionStages";
import { affectionTrack, type AffectionTrackBand } from "./affectionTrack";

const at = (percent: number) => ({ left: `${percent}%` });

function bandClass(band: AffectionTrackBand, first: boolean, last: boolean) {
  return cx(
    "absolute top-3 h-2 transition-colors",
    // A surface-colored edge parts neighbouring stages.
    !first && "border-l-2 border-surface",
    first && "rounded-l-full",
    last && "rounded-r-full",
    band.current ? "bg-gradient-accent-medium" : band.negative ? "bg-lavender-soft" : "bg-accent-soft",
  );
}

/** The -100–100 track: stage bands, boundary ticks, the 0 line, the floor and the value. */
function AffectionTrackView({ summary }: { summary: AffectionSummary }) {
  const track = affectionTrack(summary);
  const floorText = typeof summary.floor === "number" ? `，下限 ${summary.floor}` : "";
  return <div
    role="meter"
    aria-valuemin={affectionMin}
    aria-valuemax={affectionMax}
    aria-valuenow={summary.value}
    aria-valuetext={`${summary.value}，${summary.stage}${floorText}`}
    aria-label="好感"
    className="grid gap-1"
  >
    <div className="relative h-9" aria-hidden="true">
      {track.bands.map((band, index) => <span
        key={band.stage}
        className={bandClass(band, index === 0, index === track.bands.length - 1)}
        style={{ left: `${band.start}%`, width: `${band.width}%` }}
        data-current={band.current || undefined}
      />)}
      {track.ticks.map((tick) => <span key={tick} className="absolute top-5 h-1.5 w-px -translate-x-1/2 bg-line-strong" style={at(tick)} />)}
      <span className="absolute top-1 h-6 w-0.5 -translate-x-1/2 rounded-full bg-line-strong" style={at(track.zero)} data-testid="affection-track-zero" />
      {track.floor !== null && <LockSimpleIcon
        className="absolute top-6 h-3 w-3 -translate-x-1/2 text-ink-secondary"
        weight="fill"
        style={at(track.floor)}
        data-testid="affection-track-floor"
      />}
      <span
        className="absolute top-2 h-4 w-4 -translate-x-1/2 rounded-full border-2 border-surface bg-accent shadow-soft transition-[left] duration-base motion-reduce:transition-none"
        style={at(track.marker)}
        data-testid="affection-track-marker"
      />
    </div>
    <div className="relative h-5" aria-hidden="true">
      {track.bands.map((band) => <span
        key={band.stage}
        className={cx("absolute top-0 -translate-x-1/2 whitespace-nowrap text-caption", band.current ? "font-semibold text-accent-text" : "text-ink-muted")}
        style={at(band.start + band.width / 2)}
      >{band.stage}</span>)}
    </div>
  </div>;
}

/** The 「好感」 card's content: the value and stage over the whole-range track. */
export function AffectionOverview({ summary }: { summary: AffectionSummary }) {
  return <div className="grid gap-3" data-testid="role-affection-meter">
    <div className="flex items-baseline gap-3">
      <span className="font-display text-display tabular-nums text-ink">{summary.value}</span>
      <span className="text-title-sm text-accent-text">{summary.stage}</span>
    </div>
    <AffectionTrackView summary={summary} />
  </div>;
}
