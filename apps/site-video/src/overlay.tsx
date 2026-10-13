import type { CSSProperties, ReactNode } from "react";
import { useCurrentFrame } from "remotion";
import { progress } from "./screen";

/** Frames an overlay takes to pop in. */
const POP_IN = 16;

/**
 * An element drawn over a screenshot that pops in at frame `at` (fade, a
 * small rise and scale) and, with `outAt`, fades out again. Positioned
 * absolutely in screenshot pixels through `style`.
 */
export function Pop({ at, outAt, rise = 16, children, style }: { at: number; outAt?: number; rise?: number; children: ReactNode; style?: CSSProperties }) {
  const frame = useCurrentFrame();
  const shown = progress(frame, at, POP_IN) * (outAt === undefined ? 1 : 1 - progress(frame, outAt, POP_IN));
  return (
    <div
      style={{
        position: "absolute",
        opacity: shown,
        transform: `translateY(${(1 - shown) * rise}px) scale(${0.96 + shown * 0.04})`,
        ...style,
      }}
    >
      {children}
    </div>
  );
}

/** Milk-white rounded card in the app's look, for overlays. */
export const cardStyle: CSSProperties = {
  fontFamily: "var(--font-sans)",
  color: "var(--clip-ink)",
  background: "var(--clip-paper)",
  border: "1px solid var(--clip-edge)",
  borderRadius: "var(--radius-lg)",
  boxShadow: "var(--clip-card-shadow)",
};

/** A small pill label (icon + text) for overlays. */
export function Pill({ icon, children, style }: { icon?: ReactNode; children: ReactNode; style?: CSSProperties }) {
  return (
    <div
      style={{
        ...cardStyle,
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        padding: "8px 16px",
        borderRadius: 9999,
        fontSize: 17,
        whiteSpace: "nowrap",
        ...style,
      }}
    >
      {icon}
      {children}
    </div>
  );
}
