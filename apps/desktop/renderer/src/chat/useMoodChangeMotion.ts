import { useEffect, useRef, type RefObject } from "react";
import { prefersReducedMotion } from "../shared/reducedMotion";
import { moodBurstParticles, spawnMoodParticles, type MoodBurstGeometry } from "./moodBurst";
import type { MoodChangeCue } from "./useMoodChangeCue";

type UseMoodChangeMotionArgs = {
  cue: MoodChangeCue | null;
  /** Receives the particles; covers the status panel and ignores the pointer. */
  layerRef: RefObject<HTMLElement | null>;
  /** The portrait frame the particles aim at (and that dims for 难过). */
  frameRef: RefObject<HTMLElement | null>;
  pillRef: RefObject<HTMLElement | null>;
};

const easeOutSoft = "cubic-bezier(0.23, 1, 0.32, 1)";

/** A springy pop: overshoot, a small dip, settle. */
const popFrames: Keyframe[] = [
  { transform: "scale(1.16)", offset: 0.3 },
  { transform: "scale(0.95)", offset: 0.6 },
  { transform: "scale(1.02)", offset: 0.82 },
  { transform: "none" },
];

/** A short angry shake. */
const shakeFrames: Keyframe[] = [
  { transform: "translateX(-4px) scale(1.06)" },
  { transform: "translateX(4px) scale(1.06)" },
  { transform: "translateX(-3px) scale(1.03)" },
  { transform: "translateX(2px)" },
  { transform: "none" },
];

/** 难过: the portrait briefly dims and loses some colour, then recovers. */
const sadToneFrames: Keyframe[] = [
  { filter: "none" },
  { filter: "saturate(0.72) brightness(0.94)", offset: 0.3 },
  { filter: "saturate(0.72) brightness(0.94)", offset: 0.6 },
  { filter: "none" },
];

/**
 * Aims at the incoming portrait (the frame's last image; its box is capped
 * well below the frame's height in a tall panel), or the frame itself while
 * no portrait is shown.
 */
function burstGeometry(layer: HTMLElement, frame: HTMLElement, pill: HTMLElement): MoodBurstGeometry {
  const origin = layer.getBoundingClientRect();
  const portraits = frame.querySelectorAll("img");
  const frameRect = (portraits.item(portraits.length - 1) ?? frame).getBoundingClientRect();
  const pillRect = pill.getBoundingClientRect();
  return {
    frame: { x: frameRect.left - origin.left, y: frameRect.top - origin.top, width: frameRect.width, height: frameRect.height },
    pill: { x: pillRect.left - origin.left + pillRect.width / 2, y: pillRect.top - origin.top + pillRect.height / 2 },
  };
}

/**
 * Plays a mood-change cue: the pill pops (or shakes for anger), 难过 dims the
 * portrait for a moment, and the tone's particles burst. A new cue restarts
 * the pill from wherever it is, so quick changes never jump. Under reduced
 * motion nothing moves (the pill's colour change and the portrait crossfade
 * remain).
 */
export function useMoodChangeMotion({ cue, layerRef, frameRef, pillRef }: UseMoodChangeMotionArgs): void {
  const pillAnimationRef = useRef<Animation | null>(null);

  useEffect(() => {
    const layer = layerRef.current;
    const frame = frameRef.current;
    const pill = pillRef.current;
    if (!cue || !layer || !frame || !pill || prefersReducedMotion()) return;
    const shake = cue.tone === "angry";
    const from = getComputedStyle(pill).transform;
    pillAnimationRef.current?.cancel();
    pillAnimationRef.current = pill.animate(
      [{ transform: from === "none" ? "none" : from }, ...(shake ? shakeFrames : popFrames)],
      { duration: shake ? 380 : 520, easing: shake ? "linear" : easeOutSoft },
    );
    if (cue.tone === "sad") frame.animate(sadToneFrames, { duration: 1400, easing: "ease-in-out" });
    spawnMoodParticles(layer, moodBurstParticles(cue.tone, burstGeometry(layer, frame, pill)));
  }, [cue, frameRef, layerRef, pillRef]);

  // Leaving the panel drops whatever is still flying.
  useEffect(() => {
    const layer = layerRef.current;
    return () => {
      pillAnimationRef.current?.cancel();
      layer?.replaceChildren();
    };
  }, [layerRef]);
}
