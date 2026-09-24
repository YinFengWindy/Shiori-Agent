import { brandMotifPaths, type BrandMotif } from "../shared/ui/icons";
import type { MoodTone } from "./moodTone";

/**
 * The short particle burst played when a role's mood changes, built from the
 * brand motifs: 开心 → sakura petals drifting down over the portrait, 害羞 →
 * little hearts floating up, 难过 → soft droplets, 生气 → sparks flicking out
 * of the mood pill, 平静 → one sparkle twinkling with a halo.
 *
 * `moodBurstParticles` is pure (geometry + random source in, particle specs
 * out); `spawnMoodParticles` puts them into a layer with Web Animations and
 * removes each one when it finishes. Colours and glows live in styles.css
 * (`.mood-particle[data-particle][data-shade]`), so the specs only say which
 * shade to use.
 */

/** Never more than this many particles alive in one layer; the oldest go first. */
export const moodParticleCap = 28;

/** Layer-relative geometry the burst is aimed at. */
export type MoodBurstGeometry = {
  /** The portrait frame. */
  frame: { x: number; y: number; width: number; height: number };
  /** Centre of the mood pill. */
  pill: { x: number; y: number };
};

export type MoodParticleKind = BrandMotif | "halo";

/** One particle: where it starts, what it looks like and how it moves. */
export type MoodParticle = {
  kind: MoodParticleKind;
  /** Picks one of the kind's colour shades in styles.css. */
  shade: number;
  size: number;
  x: number;
  y: number;
  keyframes: Keyframe[];
  duration: number;
  delay: number;
  easing: string;
};

type Random = () => number;

const easeOutSoft = "cubic-bezier(0.23, 1, 0.32, 1)";

function between(random: Random, min: number, max: number): number {
  return min + random() * (max - min);
}

function shadeOf(random: Random, count: number): number {
  return Math.min(count - 1, Math.floor(random() * count));
}

function sign(random: Random): 1 | -1 {
  return random() < 0.5 ? -1 : 1;
}

/**
 * Petals: each drifts down across the portrait on a gentle S-curve while
 * turning. The overall timing is linear; the per-segment offsets carry the
 * sway so the path stays smooth.
 */
function petals({ frame }: MoodBurstGeometry, random: Random): MoodParticle[] {
  return Array.from({ length: 14 }, () => {
    const size = between(random, 13, 20);
    const fall = frame.height * between(random, 0.7, 1.1);
    const dx = between(random, -28, 28);
    const r0 = between(random, 0, 360);
    const dr = between(random, 120, 300) * sign(random);
    return {
      kind: "petal",
      shade: shadeOf(random, 3),
      size,
      x: frame.x + between(random, -6, frame.width - size + 6),
      y: frame.y - between(random, 6, 26),
      keyframes: [
        { transform: `translate(0px, 0px) rotate(${r0}deg)`, opacity: 0 },
        { transform: `translate(${dx * 0.6}px, ${fall * 0.28}px) rotate(${r0 + dr * 0.3}deg)`, opacity: 1, offset: 0.22 },
        { transform: `translate(${-dx * 0.4}px, ${fall * 0.65}px) rotate(${r0 + dr * 0.65}deg)`, opacity: 1, offset: 0.65 },
        { transform: `translate(${dx}px, ${fall}px) rotate(${r0 + dr}deg)`, opacity: 0 },
      ],
      duration: between(random, 1000, 1300),
      delay: between(random, 0, 220),
      easing: "linear",
    };
  });
}

/** Hearts: pop in low on the portrait and float up with a small sway. */
function hearts({ frame }: MoodBurstGeometry, random: Random): MoodParticle[] {
  return Array.from({ length: 9 }, () => {
    const up = between(random, 80, 140);
    const sway = between(random, -14, 14);
    return {
      kind: "heart",
      shade: shadeOf(random, 2),
      size: between(random, 13, 19),
      x: frame.x + frame.width / 2 + between(random, -frame.width * 0.4, frame.width * 0.32),
      y: frame.y + frame.height - between(random, 10, 70),
      keyframes: [
        { transform: "translate(0px, 0px) scale(0.3)", opacity: 0, easing: "cubic-bezier(0.2, 0.8, 0.4, 1)" },
        { transform: `translate(${sway}px, ${-up * 0.3}px) scale(1.08)`, opacity: 1, offset: 0.25 },
        { transform: `translate(${-sway}px, ${-up * 0.72}px) scale(1)`, opacity: 0.95, offset: 0.7 },
        { transform: `translate(${sway * 0.5}px, ${-up}px) scale(0.85)`, opacity: 0 },
      ],
      duration: between(random, 1100, 1300),
      delay: between(random, 0, 260),
      easing: "linear",
    };
  });
}

/** Droplets: fall straight down, stretching a little as they speed up. */
function droplets({ frame }: MoodBurstGeometry, random: Random): MoodParticle[] {
  return Array.from({ length: 12 }, () => {
    const fall = between(random, 120, 200);
    return {
      kind: "droplet",
      shade: shadeOf(random, 3),
      size: between(random, 11, 15),
      x: frame.x + between(random, 8, Math.max(8, frame.width - 18)),
      y: frame.y + between(random, -8, 60),
      keyframes: [
        { transform: "translate(0px, 0px) scaleY(0.7)", opacity: 0 },
        { transform: `translate(0px, ${fall * 0.18}px) scaleY(1)`, opacity: 0.95, offset: 0.18 },
        { transform: `translate(0px, ${fall}px) scaleY(1.15)`, opacity: 0 },
      ],
      duration: between(random, 950, 1200),
      delay: between(random, 0, 320),
      easing: "cubic-bezier(0.5, 0, 0.9, 0.6)",
    };
  });
}

/**
 * Sparks: flick out of the pill in an upward fan while it shakes. Like every
 * burst the overall timing is linear and the easing lives in the segments —
 * an overall ease-out would spend the whole flight in the first frames.
 */
function sparks({ pill }: MoodBurstGeometry, random: Random): MoodParticle[] {
  return Array.from({ length: 8 }, (_, index) => {
    const size = between(random, 10, 15);
    const angle = ((-170 + index * (160 / 7) + between(random, -8, 8)) * Math.PI) / 180;
    const distance = between(random, 30, 50);
    const dx = Math.cos(angle) * distance;
    const dy = Math.sin(angle) * distance;
    return {
      kind: "sparkle",
      // Shades 1-2 are the red sparks; shade 0 is the calm twinkle.
      shade: 1 + shadeOf(random, 2),
      size,
      x: pill.x - size / 2,
      y: pill.y - size / 2,
      keyframes: [
        { transform: "translate(0px, 0px) scale(0.3) rotate(0deg)", opacity: 0, easing: easeOutSoft },
        { transform: `translate(${dx * 0.6}px, ${dy * 0.6}px) scale(1.15) rotate(30deg)`, opacity: 1, offset: 0.3, easing: "ease-in" },
        { transform: `translate(${dx}px, ${dy}px) scale(0.2) rotate(70deg)`, opacity: 0 },
      ],
      duration: between(random, 560, 720),
      delay: between(random, 0, 80),
      easing: "linear",
    };
  });
}

/** One sparkle near the portrait's top-right corner twinkling over a soft halo. */
function twinkle({ frame }: MoodBurstGeometry): MoodParticle[] {
  const size = 30;
  const haloSize = 84;
  const x = frame.x + frame.width - 62;
  const y = frame.y + 26;
  return [
    {
      kind: "halo",
      shade: 0,
      size: haloSize,
      x: x + size / 2 - haloSize / 2,
      y: y + size / 2 - haloSize / 2,
      keyframes: [
        { transform: "scale(0.4)", opacity: 0, easing: "ease-out" },
        { transform: "scale(1)", opacity: 1, offset: 0.35, easing: "ease-in-out" },
        { transform: "scale(1.25)", opacity: 0 },
      ],
      duration: 1200,
      delay: 0,
      easing: "linear",
    },
    {
      kind: "sparkle",
      shade: 0,
      size,
      x,
      y,
      keyframes: [
        { transform: "scale(0) rotate(-25deg)", opacity: 0, easing: "cubic-bezier(0.2, 0.8, 0.4, 1.2)" },
        { transform: "scale(1.15) rotate(8deg)", opacity: 1, offset: 0.32, easing: "ease-in-out" },
        { transform: "scale(0.92) rotate(22deg)", opacity: 1, offset: 0.62, easing: "ease-in" },
        { transform: "scale(0) rotate(50deg)", opacity: 0 },
      ],
      duration: 1200,
      delay: 0,
      easing: "linear",
    },
  ];
}

const burstByTone: Record<MoodTone, (geometry: MoodBurstGeometry, random: Random) => MoodParticle[]> = {
  happy: petals,
  shy: hearts,
  sad: droplets,
  angry: sparks,
  calm: twinkle,
};

/** The particles for one mood change of `tone`. */
export function moodBurstParticles(tone: MoodTone, geometry: MoodBurstGeometry, random: Random = Math.random): MoodParticle[] {
  return burstByTone[tone](geometry, random);
}

const svgNamespace = "http://www.w3.org/2000/svg";

function particleElement(document: Document, particle: MoodParticle): HTMLElement {
  const element = document.createElement("span");
  element.className = "mood-particle";
  element.setAttribute("data-particle", particle.kind);
  element.setAttribute("data-shade", String(particle.shade));
  element.style.left = `${particle.x}px`;
  element.style.top = `${particle.y}px`;
  element.style.width = `${particle.size}px`;
  element.style.height = `${particle.size}px`;
  if (particle.kind !== "halo") {
    const svg = document.createElementNS(svgNamespace, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    const path = document.createElementNS(svgNamespace, "path");
    path.setAttribute("d", brandMotifPaths[particle.kind]);
    svg.append(path);
    element.append(svg);
  }
  return element;
}

/**
 * Adds the particles to `layer` and animates them; each removes itself when
 * its animation ends. Past `cap` live particles the oldest are dropped, so a
 * quick run of mood changes never piles up more than one burst's worth.
 */
export function spawnMoodParticles(layer: HTMLElement, particles: readonly MoodParticle[], cap = moodParticleCap): void {
  for (const particle of particles) {
    const element = particleElement(layer.ownerDocument, particle);
    layer.append(element);
    while (layer.childElementCount > cap) layer.firstElementChild?.remove();
    const animation = element.animate(particle.keyframes, {
      duration: particle.duration,
      delay: particle.delay,
      easing: particle.easing,
      fill: "both",
    });
    animation.onfinish = () => element.remove();
    animation.oncancel = () => element.remove();
  }
}
