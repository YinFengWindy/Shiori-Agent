import React, { useEffect, useLayoutEffect, useState } from "react";
import {
  advanceCrossfadeLayers,
  crossfadeDurationMs,
  initialCrossfadeLayers,
  settleCrossfadeLayers,
  type CrossfadeLayer,
} from "./crossfadeLayerState";
import { prefersReducedMotion } from "./reducedMotion";
import { cx } from "./styles";

type CrossfadeLayersProps = {
  /** The visual value (usually an image URL); empty renders nothing. */
  value: string;
  /** Classes for each stacked layer; layers are absolutely positioned over each other. */
  layerClassName?: string;
  render: (value: string) => React.ReactNode;
};

/**
 * Stacks the previous and next rendering of `value` and crossfades between
 * them (320ms, a soft blur mid-way — see `.crossfade-in/-out` in styles.css).
 * Reduced motion swaps instantly.
 */
export function CrossfadeLayers({ value, layerClassName, render }: CrossfadeLayersProps) {
  const [layers, setLayers] = useState<readonly CrossfadeLayer[]>(() => initialCrossfadeLayers(value));

  useLayoutEffect(() => {
    setLayers((current) => advanceCrossfadeLayers(current, value, prefersReducedMotion()));
  }, [value]);

  const transitioning = layers.some((layer) => layer.phase !== "static");
  useEffect(() => {
    if (!transitioning) return undefined;
    const timer = window.setTimeout(() => setLayers(settleCrossfadeLayers), crossfadeDurationMs);
    return () => window.clearTimeout(timer);
  }, [layers, transitioning]);

  return (
    <>
      {layers.map((layer) => (
        <div
          key={layer.key}
          className={cx(
            "absolute inset-0",
            layer.phase === "in" && "crossfade-in",
            layer.phase === "out" && "crossfade-out",
            layerClassName,
          )}
          aria-hidden={layer.phase === "out" || undefined}
        >
          {layer.value ? render(layer.value) : null}
        </div>
      ))}
    </>
  );
}
