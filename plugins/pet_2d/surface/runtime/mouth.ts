import type { Mouth } from "./model";
import { clamp } from "./lids";
import { geometryLimits, mouthTextureSize } from "./geometry";

/** A measured amplitude-only lip outline in the mouth's own rotated frame. */
export type MouthOutline = { upper: { x: number; y: number }[]; lower: { x: number; y: number }[]; gap: number; halfSpan: number };
/** Uses the baked articulation limit and neutral lip curvature; no phonemes are invented. */
export function mouthOutline(mouth: Mouth, amplitude: number): MouthOutline {
  const open = clamp(amplitude) * clamp(mouth.openPx / (mouth.halfWidth * mouth.openHeight));
  const gap = mouth.halfWidth * mouth.openHeight * open, halfSpan = mouth.halfWidth * (1 - 0.1 * open);
  const corner = -mouth.halfWidth * mouth.restCurve, upper = [], lower = [];
  for (let index = 0; index <= 32; index++) {
    const t = index / 16 - 1, arch = 1 - t * t;
    const y = corner + (-0.2 * gap - corner) * arch;
    upper.push({ x: t * halfSpan, y }); lower.push({ x: t * halfSpan, y: y + gap * (0.55 * arch + 0.45 * Math.sqrt(Math.max(0, arch))) });
  }
  return { upper, lower, gap, halfSpan };
}
/** Paints a small supersampled texture at the exact baked placement and angle. */
export function paintMouth(canvas: HTMLCanvasElement, mouth: Mouth, amplitude: number) {
  const scale = geometryLimits.mouthTextureScale;
  const { width, height } = mouthTextureSize(mouth.w, mouth.h);
  if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
  const ctx = canvas.getContext("2d"); if (!ctx) throw new Error("嘴部画布不可用");
  ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.setTransform(scale, 0, 0, scale, (mouth.origin.x - mouth.x) * scale, (mouth.origin.y - mouth.y) * scale); ctx.rotate(mouth.angle);
  const outline = mouthOutline(mouth, amplitude), { upper, lower, gap } = outline;
  if (gap > 0.2) {
    ctx.beginPath(); path(ctx, upper); reversePath(ctx, lower); ctx.closePath(); ctx.fillStyle = color(mouth.cavity); ctx.fill();
    ctx.save(); ctx.clip();
    ctx.beginPath(); ctx.ellipse(0, lower[16].y - gap * 0.12, outline.halfSpan * 0.58, Math.max(gap * 0.42, mouth.lineWidth), 0, 0, Math.PI * 2); ctx.fillStyle = color(mouth.tongue); ctx.fill();
    ctx.beginPath(); path(ctx, upper);
    for (let index = 32; index >= 0; index--) { const p = upper[index], t = index / 16 - 1; ctx.lineTo(p.x, p.y + gap * 0.22 * (1 - t ** 4)); }
    ctx.closePath(); ctx.fillStyle = color(mouth.cavity.map((value) => Math.round(value * 0.62))); ctx.fill(); ctx.restore();
  }
  const amount = clamp(gap / (mouth.halfWidth * mouth.openHeight));
  strokeShape(ctx, upper, mouth.lineWidth * (1 + 0.15 * amount), 0.3, 1); ctx.fillStyle = color(mouth.ink); ctx.fill();
  if (gap > 0.2) { ctx.save(); ctx.globalAlpha = Math.min(1, gap / (mouth.lineWidth * 3)) * 0.85; strokeShape(ctx, lower, mouth.lineWidth * 0.55, 0, 0.78); ctx.fill(); ctx.restore(); }
}
function color(rgb: number[]) { return `rgb(${rgb.join(",")})`; }
function path(ctx: CanvasRenderingContext2D, points: { x: number; y: number }[]) { points.forEach((point, index) => { if (index) ctx.lineTo(point.x, point.y); else ctx.moveTo(point.x, point.y); }); }
function reversePath(ctx: CanvasRenderingContext2D, points: { x: number; y: number }[]) { for (let index = points.length - 1; index >= 0; index--) ctx.lineTo(points[index].x, points[index].y); }
function strokeShape(ctx: CanvasRenderingContext2D, points: { x: number; y: number }[], width: number, corner: number, span: number) {
  const top = [], bottom = [];
  for (let index = 0; index <= 32; index++) {
    const t = index / 16 - 1; if (Math.abs(t) > span + 1e-9) continue;
    const previous = points[Math.max(0, index - 1)], next = points[Math.min(32, index + 1)], point = points[index];
    const dx = next.x - previous.x, dy = next.y - previous.y, length = Math.hypot(dx, dy) || 1;
    const radius = width / 2 * (corner + (1 - corner) * Math.sqrt(Math.max(0, 1 - (Math.abs(t) / span) ** 2.5)));
    top.push({ x: point.x + dy / length * radius, y: point.y - dx / length * radius }); bottom.push({ x: point.x - dy / length * radius, y: point.y + dx / length * radius });
  }
  ctx.beginPath(); path(ctx, top); reversePath(ctx, bottom); ctx.closePath();
}
