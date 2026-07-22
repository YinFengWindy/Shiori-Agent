export const spriteCell = { width: 192, height: 208 };

export const spriteAnimations = {
  idle: { row: 0, frames: 6, duration: 180 },
  "running-right": { row: 1, frames: 8, duration: 80 },
  "running-left": { row: 2, frames: 8, duration: 80 },
  waving: { row: 3, frames: 4, duration: 150 },
  jumping: { row: 4, frames: 5, duration: 110 },
  failed: { row: 5, frames: 8, duration: 140 },
  waiting: { row: 6, frames: 6, duration: 170 },
  running: { row: 7, frames: 6, duration: 100 },
  review: { row: 8, frames: 6, duration: 160 },
} as const;

export type SpriteState = keyof typeof spriteAnimations;

/** Resolves the background position for one fixed 192 x 208 sprite cell. */
export function spriteFramePosition(state: SpriteState, frame: number): string {
  const animation = spriteAnimations[state];
  const boundedFrame = ((frame % animation.frames) + animation.frames) % animation.frames;
  return `${-boundedFrame * spriteCell.width}px ${-animation.row * spriteCell.height}px`;
}
