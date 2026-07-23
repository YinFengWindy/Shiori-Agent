import type { ObservationStatus, PetObservationPayload } from "./types.js";
import { ObservationBubbleController } from "./bubble.js";

type DesktopObservationControllerOptions = {
  pet: {
    readonly isRunning: boolean;
    publishObservation(payload: PetObservationPayload): void;
  };
  getRoleId: () => string | null;
  getEnabled: () => boolean;
  saveEnabled: (enabled: boolean) => Promise<void>;
  bubbleDurationMs?: number;
};

/** Owns the desktop consent state and displays replies produced by the role tool. */
export class DesktopObservationController {
  private status: ObservationStatus = "off";
  private lifecycleQueue = Promise.resolve();
  private lifecycleIntent = 0;
  private targetEnabled: boolean;
  private readonly bubbles: ObservationBubbleController;

  constructor(private readonly options: DesktopObservationControllerOptions) {
    this.targetEnabled = options.getEnabled();
    this.bubbles = new ObservationBubbleController(
      (payload) => this.options.pet.publishObservation(payload),
      options.bubbleDurationMs,
    );
  }

  get state(): ObservationStatus {
    return this.status;
  }

  /** Restores persisted consent without capturing or analyzing a screen. */
  restore(): Promise<void> {
    this.targetEnabled = this.options.getEnabled();
    const intent = ++this.lifecycleIntent;
    return this.enqueue(async () => {
      if (intent !== this.lifecycleIntent) return;
      if (!this.options.getEnabled()) {
        this.publish("off", "", false, false);
        return;
      }
      if (!this.options.pet.isRunning || !this.options.getRoleId()) {
        this.publish("paused", "桌宠不可用，屏幕观察已暂停", true, true);
        return;
      }
      this.publish("observing", "", false, true);
    });
  }

  toggle(): Promise<void> {
    return this.targetEnabled ? this.stop() : this.start();
  }

  /** Grants role-tool screen observation only while a valid pet is visible. */
  start(): Promise<void> {
    this.targetEnabled = true;
    const intent = ++this.lifecycleIntent;
    return this.enqueue(async () => {
      if (intent !== this.lifecycleIntent) return;
      if (!this.options.pet.isRunning || !this.options.getRoleId()) {
        throw new Error("启用屏幕观察前必须先显示有效桌宠");
      }
      await this.options.saveEnabled(true);
      if (intent === this.lifecycleIntent) this.publish("observing", "", false, true);
    });
  }

  /** Revokes consent and clears any role-produced bubble. */
  stop(): Promise<void> {
    this.targetEnabled = false;
    const intent = ++this.lifecycleIntent;
    this.publish("off", "", false, false);
    return this.enqueue(async () => {
      if (intent !== this.lifecycleIntent) return;
      await this.options.saveEnabled(false);
      if (intent === this.lifecycleIntent) this.publish("off", "", false, false);
    });
  }

  /** Clears local display state during application shutdown without revoking consent. */
  shutdown(): Promise<void> {
    ++this.lifecycleIntent;
    this.bubbles.clear();
    return Promise.resolve();
  }

  recordUserInteraction(): void {}

  /** Dismisses the active role-generated bubble without changing consent. */
  dismissBubble(): void {
    this.bubbles.dismiss();
  }

  /** Pauses display when Windows or the pet makes the observation surface unavailable. */
  suspend(message: string): Promise<void> {
    if (!this.options.getEnabled()) return Promise.resolve();
    ++this.lifecycleIntent;
    this.publish("paused", message, true, true);
    return Promise.resolve();
  }

  /** Restores the display state after a temporary availability pause. */
  resume(): Promise<void> {
    return this.restore();
  }

  /** Displays the final reply of the role that successfully used observe_screen. */
  acceptRoleObservationReply(roleId: string, reply: string): void {
    if (
      !this.options.getEnabled()
      || this.status !== "observing"
      || !this.options.pet.isRunning
      || roleId !== this.options.getRoleId()
    ) return;
    const bubble = this.bubbles.accept(reply.slice(0, 120));
    if (bubble) this.publish("observing", bubble);
  }

  private publish(
    status: ObservationStatus,
    bubble = "",
    persistent = false,
    enabled = this.options.getEnabled(),
  ): void {
    this.status = status;
    this.bubbles.publish(status, enabled, bubble, persistent);
  }

  private enqueue(operation: () => Promise<void>): Promise<void> {
    const next = this.lifecycleQueue.then(operation, operation);
    this.lifecycleQueue = next.catch(() => undefined);
    return next;
  }
}
