import { spriteAnimations, type SpriteState } from "./spriteContract";
import type { PetReplyBubble } from "../shared/replyBubble";

/**
 * What the pet's surface accepts over the DesktopSurface state and message
 * channels, and the parsing that keeps a malformed payload from reaching React.
 *
 * The payloads cross an IPC boundary as plain structured-clone data, so they
 * arrive as `unknown` and are validated here rather than asserted. This is the
 * same defensive parsing the pre-#181 renderer did on `desktop:pet-load`; it
 * matters more now, because a surface renders in a transparent window where a
 * crash and an empty rectangle are indistinguishable to the user.
 */

/** The part of the retained state that identifies what to draw. */
export type PetSurfaceLoad = {
  package: { spritesheetUrl: string };
  state: SpriteState;
};

/** The whole retained payload: one slot, so everything durable travels together. */
export type PetSurfaceState = {
  load: PetSurfaceLoad;
  reply: PetReplyBubble | null;
};

/** A one-shot animation request. `transient` overlays and then reverts. */
export type PetSurfaceMessage = {
  state: SpriteState;
  transient: boolean;
};

function isSpriteState(value: unknown): value is SpriteState {
  return typeof value === "string" && value in spriteAnimations;
}

function readReply(value: unknown): PetReplyBubble | null {
  if (!value || typeof value !== "object") return null;
  const source = value as Partial<PetReplyBubble>;
  if (typeof source.text !== "string") return null;
  return { text: source.text, paused: source.paused === true, persistent: source.persistent === true };
}

/** Parses a retained state payload, returning null when it is unusable. */
export function readPetSurfaceState(value: unknown): PetSurfaceState | null {
  if (!value || typeof value !== "object") return null;
  const load = (value as { load?: unknown }).load;
  if (!load || typeof load !== "object") return null;
  const packageValue = (load as { package?: { spritesheetUrl?: unknown } }).package;
  const state = (load as { state?: unknown }).state;
  if (typeof packageValue?.spritesheetUrl !== "string" || !isSpriteState(state)) return null;
  return {
    load: { package: { spritesheetUrl: packageValue.spritesheetUrl }, state },
    reply: readReply((value as { reply?: unknown }).reply),
  };
}

/** Parses a transient play request, returning null when it is unusable. */
export function readPetSurfaceMessage(value: unknown): PetSurfaceMessage | null {
  if (!value || typeof value !== "object") return null;
  const state = (value as { state?: unknown }).state;
  if (!isSpriteState(state)) return null;
  return { state, transient: (value as { transient?: unknown }).transient === true };
}

/**
 * Identity of a load, used to tell "same package, new reply" from a real
 * package change. A retained payload is resent whenever *any* of its parts
 * changes, so without this an incoming bubble would restart the sprite.
 *
 * Serialized as JSON rather than joined on a separator: a spritesheet URL is
 * opaque and may contain any character, so any separator we picked could in
 * principle appear inside it and make two different loads compare equal.
 */
export function petSurfaceLoadSignature(load: PetSurfaceLoad): string {
  return JSON.stringify([load.package.spritesheetUrl, load.state]);
}
