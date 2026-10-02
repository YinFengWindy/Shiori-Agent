/** Everything that decides whether the push-to-talk hotkey may accept new input. */
export type VoiceAvailabilityInputs = {
  voiceEnabled: boolean;
  targetAvailable: boolean;
};

/** Side effects the main process applies once availability is resolved. */
export type VoiceAvailabilityEffects = {
  start(): void;
  stop(): void;
  stopAfterCurrentPress(): void;
  cancelCurrentTurn(): void;
};

/**
 * Voice input requires an explicitly available target in a ready, visible surface.
 */
export function isVoiceHotkeyAvailable({
  voiceEnabled,
  targetAvailable,
}: VoiceAvailabilityInputs): boolean {
  return voiceEnabled && targetAvailable;
}

/**
 * Applies the availability decision.
 *
 * `cancelCurrentTurn` separates the two reasons availability drops: the surface target
 * going away must abort whatever is in flight, while a settings change only
 * stops admitting new presses and lets the current one finish.
 */
export function applyVoiceAvailability(
  available: boolean,
  cancelCurrentTurn: boolean,
  effects: VoiceAvailabilityEffects,
): void {
  if (available) {
    effects.start();
    return;
  }
  if (cancelCurrentTurn) {
    effects.stop();
    effects.cancelCurrentTurn();
    return;
  }
  effects.stopAfterCurrentPress();
}
