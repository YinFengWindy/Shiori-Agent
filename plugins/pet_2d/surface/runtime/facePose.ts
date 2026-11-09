import type { FaceSample } from "../../capture/contracts";
import { clamp } from "./lids";

/** A calibrated pose used only for the currently fresh camera session. */
export type FacePose = { yaw: number; pitch: number; roll: number; eyeLeft: number; eyeRight: number; mouth: number };
/** Calibrates head rotation and smooths camera samples without retaining images. */
export class FacePoseTracker {
  private sessionId: string | null = null;
  private sequence = 0;
  private mirror = true;
  private neutral: { yaw: number; pitch: number; roll: number } | null = null;
  private latest: FaceSample | null = null;
  private pose: FacePose | null = null;
  start(sessionId: string, mirror: boolean) { this.sessionId = sessionId; this.sequence = 0; this.mirror = mirror; this.neutral = null; this.latest = null; this.pose = null; }
  stop(sessionId: string) { if (sessionId === this.sessionId) { this.sessionId = null; this.latest = null; this.pose = null; this.neutral = null; } }
  /** Drops old sessions, out-of-order frames and already-expired inference results. */
  accept(sample: FaceSample) {
    if (sample.sessionId !== this.sessionId || sample.seq <= this.sequence || !Number.isFinite(sample.capturedAt)) return;
    this.sequence = sample.seq;
    if (!sample.face || performance.now() - sample.capturedAt > 350) return;
    if (!Object.values(sample.face).every(Number.isFinite)) return;
    this.latest = sample;
    this.neutral ??= { yaw: sample.face.yaw, pitch: sample.face.pitch, roll: sample.face.roll };
  }
  /** Neutral posture lives only in this camera session and is reset on camera reopen. */
  calibrate(): boolean {
    const sample = this.latest;
    if (!sample?.face || performance.now() - sample.capturedAt > 350) return false;
    this.neutral = { yaw: sample.face.yaw, pitch: sample.face.pitch, roll: sample.face.roll }; return true;
  }
  /** Missing faces expire after 350ms, allowing the existing idle animation to resume. */
  sample(now: number, elapsed: number): FacePose | null {
    const face = this.latest?.face;
    if (!face || !this.neutral || now - this.latest!.capturedAt > 350) { this.pose = null; return null; }
    const direction = this.mirror ? -1 : 1;
    const target: FacePose = {
      yaw: clamp(angle(face.yaw - this.neutral.yaw) * direction, -0.65, 0.65), pitch: clamp(angle(face.pitch - this.neutral.pitch), -0.45, 0.45), roll: clamp(angle(face.roll - this.neutral.roll) * direction, -0.35, 0.35),
      eyeLeft: clamp(1 - (this.mirror ? face.blinkLeft : face.blinkRight)), eyeRight: clamp(1 - (this.mirror ? face.blinkRight : face.blinkLeft)), mouth: clamp((face.mouth - 0.02) / 0.6),
    };
    if (!this.pose) { this.pose = target; return target; }
    const head = 1 - Math.exp(-elapsed / 0.07), feature = 1 - Math.exp(-elapsed / 0.035);
    this.pose = { yaw: blend(this.pose.yaw, target.yaw, head), pitch: blend(this.pose.pitch, target.pitch, head), roll: blend(this.pose.roll, target.roll, head), eyeLeft: blend(this.pose.eyeLeft, target.eyeLeft, feature), eyeRight: blend(this.pose.eyeRight, target.eyeRight, feature), mouth: blend(this.pose.mouth, target.mouth, feature) };
    return this.pose;
  }
}
const angle = (value: number) => Math.atan2(Math.sin(value), Math.cos(value));
const blend = (current: number, target: number, amount: number) => current + (target - current) * amount;
