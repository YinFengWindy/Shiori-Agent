import type { BridgeEvent } from "@yinfengwindy/shiori-sdk";
import { emptyPetReply, type PetReplyBubble } from "../shared/replyBubble";
import { readRoleReply } from "./roleReply";
import type { PetReplySource } from "./voice/speechQueue";

/**
 * Identity of whoever put the current reply in the bubble slot, compared by
 * reference: a producer may only end or clear a bubble it still owns.
 */
export type BubbleOwner = { readonly source: PetReplySource; readonly runId?: string };

/**
 * Owns a visible pet's single reply slot, lock presentation and expiry.
 *
 * The latest shown reply wins the slot regardless of source. Chat replies
 * expire after a fixed duration; a held reply (live speech) stays until its
 * owner releases it, and releasing or clearing never touches a slot another
 * owner has since taken.
 */
export class ReplyBubbleController {
  private roleId = "";
  private disposed = false;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private payload = emptyPetReply;
  private owner: BubbleOwner | null = null;

  constructor(
    private readonly emit: (payload: PetReplyBubble) => void,
    private readonly durationMs = 5_000,
  ) {}

  /** Clears stale replies only when the visible role changes, not on position saves. */
  bind(roleId: string): void {
    if (this.disposed || this.roleId === roleId) return;
    this.roleId = roleId;
    this.publish(emptyPetReply, null, null);
  }

  /** Accepts final replies only from this visible pet's bound role. */
  handleEvent(event: BridgeEvent): void {
    if (this.disposed || !this.roleId) return;
    const reply = readRoleReply(event);
    if (!reply || reply.roleId !== this.roleId) return;
    this.publish({ text: reply.text, paused: false, persistent: false }, { source: "chat" }, this.durationMs);
  }

  /**
   * Shows one reply for `owner` if `roleId` is the visible pet's role; returns
   * whether it was shown. `expiryMs` null holds it until `release`.
   */
  show(owner: BubbleOwner, roleId: string, text: string, expiryMs: number | null): boolean {
    if (this.disposed || !this.roleId || roleId !== this.roleId) return false;
    this.publish({ text, paused: false, persistent: false }, owner, expiryMs);
    return true;
  }

  /** Ends a held reply now (null) or after `expiryMs`, only while `owner` still holds the slot. */
  release(owner: BubbleOwner, expiryMs: number | null): void {
    if (this.disposed || this.owner !== owner) return;
    if (expiryMs === null) { this.dismiss(); return; }
    this.startTimer(expiryMs);
  }

  /** Clears the slot only when a reply of `source` (and `runId`, when given) currently holds it. */
  clear(source: PetReplySource, runId?: string): void {
    const owner = this.owner;
    if (owner?.source === source && (runId === undefined || owner.runId === runId)) this.dismiss();
  }

  /** Presents OS lock availability without claiming screen capture is running. */
  setLocked(locked: boolean): void {
    if (this.disposed || !this.roleId) return;
    this.publish(locked
      ? { text: "Windows 已锁定", paused: true, persistent: true }
      : emptyPetReply, null, null);
  }

  /** Dismisses the message while retaining the current availability animation. */
  dismiss(): void {
    if (!this.disposed && this.payload.text) {
      this.publish({ ...this.payload, text: "", persistent: false }, null, null);
    }
  }

  /** Reclaims the timer and prevents queued callbacks from recreating a bubble. */
  dispose(): void {
    this.disposed = true;
    this.clearTimer();
    this.roleId = "";
    this.payload = emptyPetReply;
    this.owner = null;
  }

  private publish(payload: PetReplyBubble, owner: BubbleOwner | null, expiryMs: number | null): void {
    this.clearTimer();
    this.payload = payload;
    this.owner = payload.text ? owner : null;
    this.emit(payload);
    if (payload.text && expiryMs !== null) this.startTimer(expiryMs);
  }

  private startTimer(expiryMs: number): void {
    this.clearTimer();
    this.timer = setTimeout(() => this.dismiss(), expiryMs);
    this.timer.unref?.();
  }

  private clearTimer(): void {
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
  }
}
