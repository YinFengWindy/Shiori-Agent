import type { BridgeEvent } from "@yinfengwindy/shiori-sdk";
import { emptyPetReply, type PetReplyBubble } from "../shared/replyBubble";
import type { PetReplySource, ReplyOwner } from "./replyOutput";
import { readRoleReply } from "./roleReply";

/** How long a shown reply lasts: held until its owner releases it, or expiring on its own. */
export type BubbleLifetime = { kind: "hold" } | { kind: "expire"; ms: number };

/**
 * Owns a visible pet's single reply slot, lock presentation and expiry.
 *
 * The latest shown reply wins the slot regardless of source. A held reply
 * (one still being spoken) survives being covered: once the covering reply
 * expires or is dismissed, the held one is shown again, so whenever nothing
 * newer is pending the bubble matches what is being spoken. Only the owner of
 * the visible reply can end it.
 */
export class ReplyBubbleController {
  private roleId = "";
  private disposed = false;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private payload = emptyPetReply;
  private owner: ReplyOwner | null = null;
  private held: { owner: ReplyOwner; text: string } | null = null;

  constructor(
    private readonly emit: (payload: PetReplyBubble) => void,
    private readonly durationMs = 5_000,
  ) {}

  /** Clears stale replies only when the visible role changes, not on position saves. */
  bind(roleId: string): void {
    if (this.disposed || this.roleId === roleId) return;
    this.roleId = roleId;
    this.held = null;
    this.publish(emptyPetReply, null);
  }

  /** Accepts final replies only from this visible pet's bound role. */
  handleEvent(event: BridgeEvent): void {
    if (this.disposed || !this.roleId) return;
    const reply = readRoleReply(event);
    if (!reply || reply.roleId !== this.roleId) return;
    this.publish({ text: reply.text, paused: false, persistent: false }, { source: "chat" });
    this.startTimer(this.durationMs);
  }

  /** Shows one reply for `owner` if `roleId` is the visible pet's role; returns whether it was shown. */
  show(owner: ReplyOwner, roleId: string, text: string, lifetime: BubbleLifetime): boolean {
    if (this.disposed || !this.roleId || roleId !== this.roleId) return false;
    if (lifetime.kind === "hold") this.held = { owner, text };
    this.publish({ text, paused: false, persistent: false }, owner);
    if (lifetime.kind === "expire") this.startTimer(lifetime.ms);
    return true;
  }

  /** Ends `owner`'s reply now; a slot another owner has since taken is left alone. */
  release(owner: ReplyOwner): void {
    if (this.held?.owner === owner) this.held = null;
    if (!this.disposed && this.owner === owner) this.vacate();
  }

  /** Lets `owner`'s reply stay readable for `ms` more, then end; no-op once another owner took the slot. */
  releaseAfter(owner: ReplyOwner, ms: number): void {
    if (this.held?.owner === owner) this.held = null;
    if (!this.disposed && this.owner === owner) this.startTimer(ms);
  }

  /** Clears replies of `source` (and `runId`, when given), held or visible; others are untouched. */
  clear(source: PetReplySource, runId?: string): void {
    const matches = (owner: ReplyOwner) => owner.source === source && (runId === undefined || owner.runId === runId);
    if (this.held && matches(this.held.owner)) this.held = null;
    if (!this.disposed && this.owner && matches(this.owner)) this.vacate();
  }

  /** Presents OS lock availability without claiming screen capture is running. */
  setLocked(locked: boolean): void {
    if (this.disposed || !this.roleId) return;
    if (locked) this.publish({ text: "Windows 已锁定", paused: true, persistent: true }, null);
    else { this.payload = emptyPetReply; this.vacate(); }
  }

  /** User dismissal: removes the visible message, dropping it for good if it was the held one. */
  dismiss(): void {
    if (this.disposed || !this.payload.text) return;
    if (this.owner && this.owner === this.held?.owner) this.held = null;
    this.vacate();
  }

  /** Reclaims the timer and prevents queued callbacks from recreating a bubble. */
  dispose(): void {
    this.disposed = true;
    this.clearTimer();
    this.roleId = "";
    this.payload = emptyPetReply;
    this.owner = null;
    this.held = null;
  }

  /** Empties the slot, revealing a still-held reply if one was covered. */
  private vacate(): void {
    const held = this.held;
    if (held) this.publish({ text: held.text, paused: this.payload.paused, persistent: false }, held.owner);
    else this.publish({ ...this.payload, text: "", persistent: false }, null);
  }

  private publish(payload: PetReplyBubble, owner: ReplyOwner | null): void {
    this.clearTimer();
    this.payload = payload;
    this.owner = payload.text ? owner : null;
    this.emit(payload);
  }

  private startTimer(ms: number): void {
    this.clearTimer();
    this.timer = setTimeout(() => this.vacate(), ms);
    this.timer.unref?.();
  }

  private clearTimer(): void {
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
  }
}
