export const companionObservationCooldownMs = 20 * 60 * 1000;
export const companionObservationIdleThresholdSeconds = 45;
export const companionSchedulerPollMs = 30 * 1000;

type CompanionScheduleInput = {
  enabled: boolean;
  busy: boolean;
  nowMs: number;
  lastObservationAtMs: number;
  lastInteractionAtMs: number;
  idleSeconds: number;
};

/** Returns whether a persistent observation session may proactively inspect one frame. */
export function shouldRequestCompanionObservation(input: CompanionScheduleInput): boolean {
  if (!input.enabled || input.busy) return false;
  if (input.idleSeconds < companionObservationIdleThresholdSeconds) return false;
  const lastActivity = Math.max(input.lastObservationAtMs, input.lastInteractionAtMs);
  return input.nowMs - lastActivity >= companionObservationCooldownMs;
}

/** Owns the low-frequency timer while its caller supplies current activity state. */
export class CompanionScheduler {
  private timer: ReturnType<typeof setInterval> | null = null;

  constructor(
    private readonly getInput: () => CompanionScheduleInput,
    private readonly requestObservation: () => void,
  ) {}

  start(): void {
    this.stop();
    this.timer = setInterval(() => {
      if (shouldRequestCompanionObservation(this.getInput())) {
        this.requestObservation();
      }
    }, companionSchedulerPollMs);
    this.timer.unref?.();
  }

  stop(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }
}
