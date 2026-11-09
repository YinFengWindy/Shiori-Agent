import { isRecord, readPresentationIdentity, readPresentationState, type PetPresentationIdentity, type PetPresentationState } from "@yinfengwindy/shiori-pet";
import { spriteAnimations, type SpriteState } from "../surface/spriteContract";

/** Retained sprite-only load plus shared presentation state. */
export type SpritePresentation = PetPresentationIdentity & { spritesheetUrl: string; body: { width: number; height: number }; state: PetPresentationState };
/** Validates model-owned transient animation commands. */
export function readSpriteState(value: unknown): SpriteState | null { return typeof value === "string" && value in spriteAnimations ? value as SpriteState : null; }
/** Reads the provider's retained model; generic desktop_pet never sees this shape. */
export function readSpritePresentation(value: unknown): SpritePresentation | null {
  const identity = readPresentationIdentity(value);
  if (!identity || !isRecord(value) || typeof value.spritesheetUrl !== "string" || !isRecord(value.body)) return null;
  const state = readPresentationState(value.state);
  const { width, height } = value.body;
  if (!state || typeof width !== "number" || typeof height !== "number" || !Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) return null;
  return { ...identity, spritesheetUrl: value.spritesheetUrl, body: { width, height }, state };
}
