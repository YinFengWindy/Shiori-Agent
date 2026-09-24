import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  advanceCrossfadeLayers,
  crossfadeDurations,
  initialCrossfadeLayers,
  settleCrossfadeLayers,
  type CrossfadeLayer,
  type CrossfadeVariant,
} from "./crossfadeLayerState";
import { cx } from "./styles";

type CrossfadeLayersProps = {
  /** The visual value (usually an image URL); empty renders nothing. */
  value: string;
  /** `soft` (default) crossfades; `focus` also settles the new image from a slight zoom and blur. */
  variant?: CrossfadeVariant;
  /**
   * What the value belongs to (e.g. the role). When it changes the new value
   * replaces the old one outright — a role switch is animated by its view
   * transition, a same-subject change (a new mood, a new background) here.
   */
  resetKey?: string;
  /** Classes for each stacked layer; layers are absolutely positioned over each other. */
  layerClassName?: string;
  render: (value: string) => React.ReactNode;
};

/**
 * Stacks the previous and next rendering of `value` and crossfades between
 * them (see `.crossfade-*` in styles.css). Reduced motion keeps only the
 * opacity fade.
 */
export function CrossfadeLayers({ value, variant = "soft", resetKey = "", layerClassName, render }: CrossfadeLayersProps) {
  const [layers, setLayers] = useState<readonly CrossfadeLayer[]>(() => initialCrossfadeLayers(value));
  const resetKeyRef = useRef(resetKey);

  useLayoutEffect(() => {
    const subjectChanged = resetKeyRef.current !== resetKey;
    resetKeyRef.current = resetKey;
    setLayers((current) => advanceCrossfadeLayers(current, value, subjectChanged));
  }, [value, resetKey]);

  const transitioning = layers.some((layer) => layer.phase !== "static");
  useEffect(() => {
    if (!transitioning) return undefined;
    const timer = window.setTimeout(() => setLayers(settleCrossfadeLayers), crossfadeDurations[variant]);
    return () => window.clearTimeout(timer);
  }, [layers, transitioning, variant]);

  return (
    <>
      {layers.map((layer) => (
        <div
          key={layer.key}
          className={cx(
            "absolute inset-0",
            layer.phase === "in" && (variant === "focus" ? "crossfade-in-focus" : "crossfade-in"),
            layer.phase === "out" && (variant === "focus" ? "crossfade-out-focus" : "crossfade-out"),
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
