/**
 * Layer bookkeeping for crossfading one visual value (an image URL) into the
 * next: the outgoing layer fades out on top of the incoming one fading in,
 * then the finished layers settle into a single static one. Pure so the
 * transitions are testable; `CrossfadeLayers` drives it.
 */

/** Crossfade length; matches `--duration-crossfade` in styles.css. */
export const crossfadeDurationMs = 320;

export type CrossfadeLayer = {
  /** Stable React key; every new value gets a new one. */
  key: number;
  value: string;
  phase: "static" | "in" | "out";
};

/** The single layer a crossfade starts from. */
export function initialCrossfadeLayers(value: string): CrossfadeLayer[] {
  return [{ key: 0, value, phase: "static" }];
}

/**
 * Moves to `value`. The currently shown layer fades out and the new one fades
 * in; layers already fading out are dropped (a rapid second change jumps
 * straight from the newest pair). With `instant` (reduced motion, or no image
 * shown before) the new value simply replaces everything.
 */
export function advanceCrossfadeLayers(
  layers: readonly CrossfadeLayer[],
  value: string,
  instant: boolean,
): CrossfadeLayer[] | readonly CrossfadeLayer[] {
  const current = [...layers].reverse().find((layer) => layer.phase !== "out");
  if (current?.value === value) return layers;
  const key = Math.max(0, ...layers.map((layer) => layer.key)) + 1;
  if (instant || !current?.value) return [{ key, value, phase: "static" }];
  return [{ ...current, phase: "out" }, { key, value, phase: "in" }];
}

/** Ends a crossfade: drops the faded-out layers and freezes the incoming one. */
export function settleCrossfadeLayers(layers: readonly CrossfadeLayer[]): CrossfadeLayer[] | readonly CrossfadeLayer[] {
  if (layers.every((layer) => layer.phase === "static")) return layers;
  return layers
    .filter((layer) => layer.phase !== "out")
    .map((layer) => ({ ...layer, phase: "static" as const }));
}
