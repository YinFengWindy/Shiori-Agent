import type { ObservationStatus, PetObservationPayload } from "./types.js";

const defaultBubbleDurationMs = 5_000;

/** Owns safe bubble visibility and expiry. */
export class ObservationBubbleController {
  private timer: ReturnType<typeof setTimeout> | null = null;
  private payload: PetObservationPayload = {
    status: "off",
    enabled: false,
    bubble: "",
    persistent: false,
  };

  constructor(
    private readonly emit: (payload: PetObservationPayload) => void,
    private readonly durationMs = defaultBubbleDurationMs,
  ) {}

  publish(
    status: ObservationStatus,
    enabled: boolean,
    bubble = "",
    persistent = false,
  ): void {
    this.clearTimer();
    this.payload = { status, enabled, bubble, persistent };
    this.emit(this.payload);
    if (bubble && !persistent) {
      this.timer = setTimeout(() => {
        if (this.payload.bubble !== bubble) return;
        this.publish(this.payload.status, this.payload.enabled);
      }, this.durationMs);
      this.timer.unref?.();
    }
  }

  dismiss(): void {
    if (!this.payload.bubble) return;
    this.publish(this.payload.status, this.payload.enabled);
  }

  clear(): void {
    this.clearTimer();
    this.payload = { ...this.payload, bubble: "", persistent: false };
  }

  private clearTimer(): void {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
  }
}
