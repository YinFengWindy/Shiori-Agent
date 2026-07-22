export const spriteCell = { width: 192, height: 208 };

export const spriteAnimations = {
  idle: { row: 0, frames: 6, frameDurations: [280, 110, 110, 140, 140, 320] },
  "running-right": { row: 1, frames: 8, frameDurations: [120, 120, 120, 120, 120, 120, 120, 220] },
  "running-left": { row: 2, frames: 8, frameDurations: [120, 120, 120, 120, 120, 120, 120, 220] },
  waving: { row: 3, frames: 4, frameDurations: [140, 140, 140, 280] },
  jumping: { row: 4, frames: 5, frameDurations: [140, 140, 140, 140, 280] },
  failed: { row: 5, frames: 8, frameDurations: [140, 140, 140, 140, 140, 140, 140, 240] },
  waiting: { row: 6, frames: 6, frameDurations: [150, 150, 150, 150, 150, 260] },
  running: { row: 7, frames: 6, frameDurations: [120, 120, 120, 120, 120, 220] },
  review: { row: 8, frames: 6, frameDurations: [150, 150, 150, 150, 150, 280] },
} as const;

export type SpriteState = keyof typeof spriteAnimations;

/** Resolves the background position for one fixed 192 x 208 sprite cell. */
export function spriteFramePosition(state: SpriteState, frame: number): string {
  const animation = spriteAnimations[state];
  const boundedFrame = ((frame % animation.frames) + animation.frames) % animation.frames;
  return `${-boundedFrame * spriteCell.width}px ${-animation.row * spriteCell.height}px`;
}
