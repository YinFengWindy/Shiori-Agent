import type { EyeAnchor, Layer, Lid } from "./model";
import { gridIndices, type Mesh } from "./mesh";

/** Clamps a model parameter to its valid interval. */
export function clamp(value: number, low = 0, high = 1): number { return Math.max(low, Math.min(high, value)); }
/** Smooth blend with zero slope at either endpoint. */
export function smooth(value: number): number { const t = clamp(value); return t * t * (3 - 2 * t); }
const polynomial = (coefficients: number[], x: number) => coefficients[0] + coefficients[1] * x + coefficients[2] * x * x;

function frame(eye: EyeAnchor, x: number, y: number) {
  const cos = Math.cos(eye.angle), sin = Math.sin(eye.angle), dx = x - eye.closeX, dy = y - eye.closeY;
  return { u: dx * cos + dy * sin, v: -dx * sin + dy * cos, cos, sin };
}
function band(lid: Lid, u: number, closed: number) {
  const at = clamp((u - lid.low) / (lid.high - lid.low)) * (lid.band.length - 1), index = Math.min(lid.band.length - 2, Math.floor(at)), fraction = at - index;
  const measured = clamp(lid.band[index] * (1 - fraction) + lid.band[index + 1] * fraction, 0, lid.opening);
  const taper = Math.pow(clamp(Math.min(u - lid.low, lid.high - u) / (0.35 * lid.scale)), 0.7);
  return measured * (1 - closed) + lid.weight * taper * closed;
}
function curve(lid: Lid, u: number, openness: number) {
  const t = clamp(u, lid.low, lid.high) / lid.scale;
  const lower = polynomial(lid.lower, t), edge = Math.min(polynomial(lid.edge, t), lower - 0.5);
  return { lower, edge, upper: edge * openness + lower * (1 - openness) };
}

/** Deforms eye white or lash ink in the baked, rotated eye frame. */
export function deformLid(lid: Lid, eye: EyeAnchor, x: number, y: number, openness: number, ink = false): [number, number] {
  const f = frame(eye, x, y), { lower, edge, upper } = curve(lid, f.u, openness);
  const before = band(lid, f.u, 0), after = band(lid, f.u, 1 - openness), start = edge - before;
  let v: number;
  if (ink) {
    const distance = f.v - start;
    v = upper - after + distance * (distance < 0 ? 1 - 2 * smooth((1 - openness - 0.55) / 0.45) : 1);
  } else {
    const reach = 1.5 * lid.opening, rim = Math.max(1.5, 0.5 * lid.opening), rimScale = openness + (1 - openness) * 0.1;
    if (f.v <= start) v = f.v + (upper - after - start) * (1 - smooth((start - f.v) / reach));
    else if (f.v <= edge) v = upper - after + (f.v - start) * (before > 1e-6 ? after / before : 0);
    else if (f.v <= lower) v = upper + (f.v - edge) * (lower - upper) / (lower - edge);
    else if (f.v <= lower + rim) v = lower + (f.v - lower) * rimScale;
    else v = f.v + (rim * (rimScale - 1)) * (1 - smooth((f.v - lower - rim) / reach));
  }
  const outside = Math.max(0, lid.low - f.u, f.u - lid.high) / lid.scale;
  v = f.v + (v - f.v) * (1 - smooth(outside / 0.25));
  return [eye.closeX + f.u * f.cos - v * f.sin, eye.closeY + f.u * f.sin + v * f.cos];
}

/** Four antialiased rows follow the measured upper-lid contour and thickness. */
export function lidLinePoint(lid: Lid, eye: EyeAnchor, u: number, row: number, openness: number): [number, number] {
  const center = (at: number) => { const c = curve(lid, at, openness), width = band(lid, at, 1 - openness); return { v: c.upper - width / 2, width }; };
  const sample = center(u), slope = center(u + 0.5).v - center(u - 0.5).v, half = sample.width / 2;
  const offset = row === 0 ? -(half + 0.5) : row === 3 ? half + 0.5 : (row === 1 ? -1 : 1) * Math.max(0, half - 0.5);
  const v = sample.v + offset * Math.hypot(1, slope), cos = Math.cos(eye.angle), sin = Math.sin(eye.angle);
  return [eye.closeX + u * cos - v * sin, eye.closeY + u * sin + v * cos];
}

/** Creates a generated contour mesh; its colors and taper still come from the bake. */
export function lidLineMesh(owner: Layer, lid: Lid, eye: EyeAnchor): Mesh {
  const columns = Math.max(2, Math.ceil(lid.high - lid.low) + 1), base = new Float32Array(columns * 4 * 2), uvs = new Float32Array(base.length), pixels = new Uint8Array(columns * 2 * 4);
  for (let col = 0; col < columns; col++) {
    const u = lid.low + (lid.high - lid.low) * col / (columns - 1);
    for (let row = 0; row < 4; row++) {
      const at = (row * columns + col) * 2; base.set(lidLinePoint(lid, eye, u, row, 1), at); uvs[at] = (col + 0.5) / columns; uvs[at + 1] = row === 0 || row === 3 ? 0.25 : 0.75;
    }
    for (let row = 0; row < 2; row++) { const at = (row * columns + col) * 4; pixels.set(lid.colour, at); pixels[at + 3] = row ? Math.round(255 * clamp(Math.min(band(lid, u, 0), band(lid, u, 1)))) : 0; }
  }
  return { layer: { ...owner, name: `${owner.name}:line` }, base, positions: new Float32Array(base), uvs, indices: gridIndices(columns, 4), image: { width: columns, height: 2, pixels }, part: "line", lid, lineColumns: columns };
}
