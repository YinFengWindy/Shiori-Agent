import type { HairPins } from "./model";
import { clamp } from "./lids";

/** Two damped responses per baked strand preserve both root stiffness and soft tips. */
export type HairMotion = { stiff: { position: number; velocity: number; offset: number }; soft: { position: number; velocity: number; offset: number }; phase: number }[];
/** Local head/body displacement drives inertia; wind and response stay tunable. */
export type HairDrive = { displacement: number; strength: number; stiffness: number; damping: number };
/** Creates private simulation state; the immutable bake is never modified. */
export function createHairMotion(pins: HairPins): HairMotion { return pins.strands.map((_, index) => ({ stiff: { position: 0, velocity: 0, offset: 0 }, soft: { position: 0, velocity: 0, offset: 0 }, phase: index * 1.37 + pins.layer })); }
/** Integrates springs in bounded substeps so a delayed frame cannot explode the mesh. */
export function stepHair(motion: HairMotion, seconds: number, elapsed: number, faceScale: number, enabled: boolean, drive: HairDrive = { displacement: 0, strength: 1, stiffness: 1, damping: 1 }) {
  const dt = Math.min(0.05, Math.max(0, elapsed)), steps = Math.max(1, Math.ceil(dt * 120));
  for (const strand of motion) {
    const wind = (3.6 * Math.sin(seconds * 0.8 + strand.phase) + 2 * Math.sin(seconds * 1.9 + strand.phase * 2.3)) * faceScale;
    const target = drive.displacement + wind;
    for (const [spring, stiffness, damping, gain, maximum] of [[strand.stiff, 75, 11, 1.35, 20], [strand.soft, 24, 2.8, 1.65, 26]] as const) {
      if (!enabled || drive.strength === 0) { spring.position = target; spring.velocity = 0; spring.offset = 0; continue; }
      for (let i = 0; i < steps; i++) { spring.velocity += (-stiffness * drive.stiffness * (spring.position - target) - damping * drive.damping * spring.velocity) * dt / steps; spring.position += spring.velocity * dt / steps; }
      spring.offset = clamp(((spring.position - target) * gain + wind * 0.55) * drive.strength, -maximum * faceScale, maximum * faceScale);
    }
  }
}
/** Enforces every baked travel bound, including arc shortening and radial cap. */
export function constrainHair(pins: HairPins, vertex: number, dx: number, dy = 0): [number, number] {
  const x = clamp(dx, pins.lo[vertex], pins.hi[vertex]), y = dy - x * x / (2 * Math.max(1, pins.hang[vertex]));
  const length = Math.hypot(x, y), scale = length > pins.cap[vertex] ? pins.cap[vertex] / length : 1;
  return [x * scale, y * scale];
}
/** Blends stored strand weights and per-vertex freedom without replacing their attachment data. */
export function hairDisplacement(pins: HairPins, motion: HairMotion, vertex: number): [number, number] {
  const freedom = pins.freedom[vertex]; if (freedom <= 0) return [0, 0];
  const softness = pins.kind === "front" ? 0.4 : pins.kind === "accessory" ? 0.8 : 2;
  const blend = Math.min(1, Math.pow(freedom, 1.2) * softness); let displacement = 0;
  for (let index = 0; index < motion.length; index++) displacement += pins.weights[vertex * motion.length + index] * (motion[index].stiff.offset * (1 - blend) + motion[index].soft.offset * blend);
  return constrainHair(pins, vertex, displacement * freedom * (pins.kind === "accessory" ? 1.4 : 2));
}
