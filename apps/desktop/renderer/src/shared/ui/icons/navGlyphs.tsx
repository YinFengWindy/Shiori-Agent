import type React from "react";
import { useId } from "react";
import {
  BookOpenText,
  Chats,
  GearSix,
  MagnifyingGlass,
  Users,
  type Icon,
} from "@phosphor-icons/react";

/**
 * Nav rail glyphs: the Phosphor *regular* glyph, outline untouched, with one
 * brand motif (sparkle, heart, ribbon, sakura, bookmark) tucked inside it.
 *
 * - The motif is a separate `<g class="nav-glyph-motif …">` drawn over the
 *   glyph in Phosphor's 256 viewBox. Idle it is `--color-motif` (pink-500);
 *   inside an `aria-current="page"` trigger it switches to the brand
 *   gradient, whose id is unique per instance (`useId`).
 * - The glyph stroke is `currentColor`, so the rail's muted / ink / accent
 *   states apply unchanged.
 * - A one-shot animation plays on the motif only, on hover / keyboard focus
 *   of the enclosing button and when it becomes current. The keyframes live
 *   in `styles.css` behind `prefers-reduced-motion: no-preference`, so reduced
 *   motion keeps only the colour change.
 *
 * Every glyph satisfies the plugin nav icon contract
 * (`React.ComponentType<{ className?: string }>`), so plugins can use these
 * directly or build their own with `withMotif`.
 */

/** Which one-shot animation the motif plays (see `.nav-glyph-motif--*` in styles.css). */
export type NavGlyphMotion = "twinkle" | "beat" | "wiggle" | "spin" | "flutter";

/** Four-point sparkle (the brand SparkleIcon outline) centred at (cx, cy) with radius r, in 256 space. */
export function sparklePath(cx: number, cy: number, r: number): string {
  const k = r * 0.26;
  return `M${cx} ${cy - r} Q${cx + k} ${cy - k} ${cx + r} ${cy} Q${cx + k} ${cy + k} ${cx} ${cy + r} Q${cx - k} ${cy + k} ${cx - r} ${cy} Q${cx - k} ${cy - k} ${cx} ${cy - r}Z`;
}

/** Brand motifs in the 256 viewBox; each returns the motif's inner shapes. */
export const navMotifs = {
  /** Sparkle with a small companion dot (the dot fades while the sparkle twinkles). */
  sparkle(cx: number, cy: number, r: number, dot?: { cx: number; cy: number; r: number }) {
    return (
      <>
        <path className="nav-glyph-motif-sparkle" d={sparklePath(cx, cy, r)} />
        {dot ? <circle className="nav-glyph-motif-dot" cx={dot.cx} cy={dot.cy} r={dot.r} /> : null}
      </>
    );
  },
  heart(cx: number, cy: number, scale: number) {
    return (
      <path
        transform={`translate(${cx} ${cy}) scale(${scale})`}
        d="M0 9 C-2 7 -10 2 -10 -3.5 C-10 -7.5 -7 -10 -4 -10 C-2 -10 -0.6 -9 0 -7.6 C0.6 -9 2 -10 4 -10 C7 -10 10 -7.5 10 -3.5 C10 2 2 7 0 9Z"
      />
    );
  },
  /** The brand RibbonIcon bow (24 space) rescaled around (cx, cy). */
  ribbon(cx: number, cy: number, scale: number) {
    return (
      <g transform={`translate(${cx} ${cy}) scale(${scale}) translate(-12 -12)`}>
        <path d="M10.4 12 C9.4 9.6 7 8.2 5.1 9.1 C3.6 10 3.6 14 5.1 14.9 C7 15.8 9.4 14.4 10.4 12 Z M13.6 12 C14.6 9.6 17 8.2 18.9 9.1 C20.4 10 20.4 14 18.9 14.9 C17 15.8 14.6 14.4 13.6 12 Z" />
        <rect x="10" y="10" width="4" height="4" rx="1.5" />
      </g>
    );
  },
  /** Five notched sakura petals with a light core. */
  sakura(cx: number, cy: number, r: number) {
    const petal = `M0 0 C${-r * 0.55} ${-r * 0.35} ${-r * 0.5} ${-r * 0.95} ${-r * 0.18} ${-r} L0 ${-r * 0.82} L${r * 0.18} ${-r} C${r * 0.5} ${-r * 0.95} ${r * 0.55} ${-r * 0.35} 0 0Z`;
    return (
      <g transform={`translate(${cx} ${cy})`}>
        {[0, 1, 2, 3, 4].map((index) => <path key={index} transform={`rotate(${index * 72})`} d={petal} />)}
        <circle className="nav-glyph-core" r={r * 0.16} />
      </g>
    );
  },
  /** Notched ribbon bookmark hanging from (x, top). */
  bookmark(x: number, top: number, width: number, height: number) {
    return <path d={`M${x} ${top} h${width} v${height} l${-width / 2} ${-width * 0.45} l${-width / 2} ${width * 0.45}Z`} />;
  },
};

/** Builds a nav glyph from a Phosphor base icon and one motif drawn in its 256 viewBox. */
export function withMotif(Base: Icon, motif: React.ReactNode, motion: NavGlyphMotion, displayName: string) {
  function NavGlyph({ className }: { className?: string }) {
    const gradientId = `nav-motif-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
    return (
      <svg className={["nav-glyph", className].filter(Boolean).join(" ")} viewBox="0 0 256 256" fill="currentColor" aria-hidden="true">
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" style={{ stopColor: "var(--color-motif-gradient-start)" }} />
            <stop offset="0.5" style={{ stopColor: "var(--color-motif-gradient-mid)" }} />
            <stop offset="1" style={{ stopColor: "var(--color-motif-gradient-end)" }} />
          </linearGradient>
        </defs>
        <Base size={256} weight="regular" />
        <g
          className={`nav-glyph-motif nav-glyph-motif--${motion}`}
          style={{ "--nav-motif-gradient": `url(#${gradientId})` } as React.CSSProperties}
        >
          {motif}
        </g>
      </svg>
    );
  }
  NavGlyph.displayName = displayName;
  return NavGlyph;
}

/** 搜索: a sparkle in the lens. */
export const SearchGlyph = withMotif(MagnifyingGlass, navMotifs.sparkle(88, 88, 30, { cx: 128, cy: 70, r: 7 }), "twinkle", "SearchGlyph");
/** 消息: a heart in the back bubble. */
export const ChatsGlyph = withMotif(Chats, navMotifs.heart(104, 94, 3.1), "beat", "ChatsGlyph");
/** 角色: a ribbon bow on the front head. */
export const RolesGlyph = withMotif(Users, navMotifs.ribbon(84, 58, 5.2), "wiggle", "RolesGlyph");
/** 设置: a sakura in the gear hole. */
export const SettingsGlyph = withMotif(GearSix, navMotifs.sakura(128, 128, 27), "spin", "SettingsGlyph");
/** 故事 (story plugin): a bookmark on the left page. */
export const StoryGlyph = withMotif(BookOpenText, navMotifs.bookmark(52, 36, 30, 96), "flutter", "StoryGlyph");
