import type { BridgeEvent } from "../../../apps/desktop/src/bridge/shared";
import { emptyPetReply, type PetReplyBubble } from "../shared/replyBubble";
import { readRoleReply } from "./roleReply";

/** Owns a visible pet's replies, lock presentation, and five-second expiry. */
export class ReplyBubbleController {
  private roleId = "";
  private disposed = false;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private payload = emptyPetReply;

  constructor(
    private readonly emit: (payload: PetReplyBubble) => void,
    private readonly durationMs = 5_000,
  ) {}

  /** Clears stale replies only when the visible role changes, not on position saves. */
  bind(roleId: string): void {
    if (this.disposed || this.roleId === roleId) return;
    this.roleId = roleId;
    this.publish(emptyPetReply);
  }

  /** Accepts final replies only from this visible pet's bound role. */
  handleEvent(event: BridgeEvent): void {
    if (this.disposed || !this.roleId) return;
    const reply = readRoleReply(event);
    if (!reply || reply.roleId !== this.roleId) return;
    this.publish({ text: reply.text, paused: false, persistent: false });
  }

  /** Presents OS lock availability without claiming screen capture is running. */
  setLocked(locked: boolean): void {
    if (this.disposed || !this.roleId) return;
    this.publish(locked
      ? { text: "Windows 已锁定", paused: true, persistent: true }
      : emptyPetReply);
  }

  /** Dismisses the message while retaining the current availability animation. */
  dismiss(): void {
    if (!this.disposed && this.payload.text) {
      this.publish({ ...this.payload, text: "", persistent: false });
    }
  }

  /** Reclaims the timer and prevents queued callbacks from recreating a bubble. */
  dispose(): void {
    this.disposed = true;
    this.clearTimer();
    this.roleId = "";
    this.payload = emptyPetReply;
  }

  private publish(payload: PetReplyBubble): void {
    this.clearTimer();
    this.payload = payload;
    this.emit(payload);
    if (payload.text && !payload.persistent) {
      this.timer = setTimeout(() => this.dismiss(), this.durationMs);
      this.timer.unref?.();
    }
  }

  private clearTimer(): void {
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
  }
}
