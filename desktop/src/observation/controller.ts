import type { ObservationStatus, PetObservationPayload } from "./types.js";
import { ObservationBubbleController } from "./bubble.js";

type DesktopObservationControllerOptions = {
  pet: {
    readonly isRunning: boolean;
    publishObservation(payload: PetObservationPayload): void;
  };
  getRoleId: () => string | null;
  bubbleDurationMs?: number;
};

/** Displays replies produced by the role-owned screen observation tool. */
export class DesktopObservationController {
  private status: ObservationStatus = "off";
  private lifecycleQueue = Promise.resolve();
  private lifecycleIntent = 0;
  private readonly bubbles: ObservationBubbleController;

  constructor(private readonly options: DesktopObservationControllerOptions) {
    this.bubbles = new ObservationBubbleController(
      (payload) => this.options.pet.publishObservation(payload),
      options.bubbleDurationMs,
    );
  }

  get state(): ObservationStatus {
    return this.status;
  }

  /** Synchronizes the local bubble surface without affecting role capabilities. */
  restore(): Promise<void> {
    const intent = ++this.lifecycleIntent;
    return this.enqueue(async () => {
      if (intent !== this.lifecycleIntent) return;
      if (!this.options.pet.isRunning || !this.options.getRoleId()) {
        this.publish("off");
        return;
      }
      this.publish("observing");
    });
  }

  /** Clears local display state during application shutdown. */
  shutdown(): Promise<void> {
    ++this.lifecycleIntent;
    this.bubbles.clear();
    return Promise.resolve();
  }

  /** Dismisses the active role-generated bubble. */
  dismissBubble(): void {
    this.bubbles.dismiss();
  }

  /** Pauses the bubble surface while Windows is unavailable. */
  suspend(message: string): Promise<void> {
    ++this.lifecycleIntent;
    if (this.options.pet.isRunning) this.publish("paused", message, true);
    return Promise.resolve();
  }

  /** Restores the display state after a temporary availability pause. */
  resume(): Promise<void> {
    return this.restore();
  }

  /** Displays the final desktop reply from the role bound to the visible pet. */
  acceptRoleReply(roleId: string, reply: string): void {
    if (
      !this.options.pet.isRunning
      || roleId !== this.options.getRoleId()
    ) return;
    const bubble = this.bubbles.accept(reply.slice(0, 120));
    if (bubble) this.publish("observing", bubble);
  }

  private publish(
    status: ObservationStatus,
    bubble = "",
    persistent = false,
  ): void {
    this.status = status;
    this.bubbles.publish(status, true, bubble, persistent);
  }

  private enqueue(operation: () => Promise<void>): Promise<void> {
    const next = this.lifecycleQueue.then(operation, operation);
    this.lifecycleQueue = next.catch(() => undefined);
    return next;
  }
}
