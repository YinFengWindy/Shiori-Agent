import { randomUUID } from "node:crypto";
import type { BridgeRequest, BridgeResponse } from "../shared.js";
import {
  PrimaryDisplayUnavailableError,
  type CapturedObservationFrame,
  type ObservationResult,
  type ObservationStatus,
  type PetObservationPayload,
} from "./types.js";
import { reduceObservationEpisode, type ObservationEpisode } from "./episode.js";
import { ObservationBubbleController } from "./bubble.js";
import { requestObservationResult } from "./request.js";
import { CompanionScheduler } from "./scheduler.js";

type DesktopObservationControllerOptions = {
  bridge: {
    invoke(request: Omit<BridgeRequest, "id">): Promise<{
      payload: Record<string, unknown>;
      error: BridgeResponse["error"];
    }>;
  };
  pet: {
    readonly isRunning: boolean;
    publishObservation(payload: PetObservationPayload): void;
  };
  getRoleId: () => string | null;
  getEnabled: () => boolean;
  saveEnabled: (enabled: boolean) => Promise<void>;
  captureFrame: () => Promise<CapturedObservationFrame>;
  getIdleSeconds: () => number;
  now?: () => number;
  bubbleDurationMs?: number;
  onError?: (error: unknown) => void;
};

type ObservationSessionSnapshot = {
  roleId: string;
  sessionId: string;
  episode: ObservationEpisode | null;
};

type ActiveObservationRequest = {
  generation: number;
  promise: Promise<void>;
};

/** Owns one primary-screen observation session and its ephemeral model state. */
export class DesktopObservationController {
  private status: ObservationStatus = "off";
  private lifecycleQueue = Promise.resolve();
  private lifecycleIntent = 0;
  private targetEnabled: boolean;
  private activeRequest: ActiveObservationRequest | null = null;
  private lastObservationAtMs = 0;
  private lastInteractionAtMs = 0;
  private generation = 0;
  private sessionId = "";
  private sessionRoleId = "";
  private episodeIndex = 0;
  private episode: ObservationEpisode | null = null;
  private latestResult: ObservationResult | null = null;
  private readonly now: () => number;
  private readonly bubbles: ObservationBubbleController;
  private readonly scheduler: CompanionScheduler;

  constructor(private readonly options: DesktopObservationControllerOptions) {
    this.now = options.now ?? Date.now;
    this.targetEnabled = options.getEnabled();
    this.bubbles = new ObservationBubbleController(
      (payload) => this.options.pet.publishObservation(payload),
      options.bubbleDurationMs,
    );
    this.scheduler = new CompanionScheduler(
      () => ({
        enabled: this.options.getEnabled(),
        busy: this.activeRequest?.generation === this.generation,
        nowMs: this.now(),
        lastObservationAtMs: this.lastObservationAtMs,
        lastInteractionAtMs: this.lastInteractionAtMs,
        idleSeconds: this.options.getIdleSeconds(),
      }),
      () => this.requestDetachedObservation(),
    );
  }

  get state(): ObservationStatus {
    return this.status;
  }

  restore(): Promise<void> {
    this.targetEnabled = this.options.getEnabled();
    const intent = ++this.lifecycleIntent;
    return this.enqueueLifecycle(async () => {
      if (intent !== this.lifecycleIntent) return;
      if (!this.options.getEnabled()) {
        const snapshot = this.invalidateSession();
        this.publish("off", "", false, false);
        await this.settleSnapshot(snapshot);
        return;
      }
      const roleId = this.options.getRoleId();
      if (!this.options.pet.isRunning || !roleId) {
        const snapshot = this.invalidateSession();
        this.publish("paused", "桌宠不可用，屏幕观察已暂停", true, true);
        await this.settleSnapshot(snapshot);
        return;
      }
      if (this.sessionId && this.sessionRoleId === roleId) {
        this.bubbles.republish(this.status, true);
        return;
      }
      const snapshot = this.invalidateSession();
      await this.settleSnapshot(snapshot);
      if (intent !== this.lifecycleIntent) return;
      this.startSession(roleId);
    });
  }

  toggle(): Promise<void> {
    return this.targetEnabled ? this.stop() : this.start();
  }

  start(): Promise<void> {
    this.targetEnabled = true;
    const intent = ++this.lifecycleIntent;
    return this.enqueueLifecycle(async () => {
      if (intent !== this.lifecycleIntent) return;
      const roleId = this.options.getRoleId();
      if (!this.options.pet.isRunning || !roleId) {
        throw new Error("启用屏幕观察前必须先显示有效桌宠");
      }
      await this.options.saveEnabled(true);
      if (intent !== this.lifecycleIntent) return;
      this.startSession(roleId);
      this.requestDetachedObservation();
    });
  }

  stop(): Promise<void> {
    this.targetEnabled = false;
    const intent = ++this.lifecycleIntent;
    const immediateSnapshot = this.invalidateSession();
    this.publish("off", "", false, false);
    return this.enqueueLifecycle(async () => {
      const queuedSnapshot = this.invalidateSession();
      let settlementError: unknown;
      try {
        await this.settleSnapshots(immediateSnapshot, queuedSnapshot);
      } catch (error) {
        settlementError = error;
      }
      if (intent !== this.lifecycleIntent) return;
      await this.options.saveEnabled(false);
      if (settlementError) {
        this.publish("failed", "观察经历保存失败", true, false);
        throw settlementError;
      }
      this.publish("off", "", false, false);
    });
  }

  /** Settles the active episode during application shutdown without clearing persisted consent. */
  shutdown(): Promise<void> {
    ++this.lifecycleIntent;
    const immediateSnapshot = this.invalidateSession();
    return this.enqueueLifecycle(async () => {
      const queuedSnapshot = this.invalidateSession();
      await this.settleSnapshots(immediateSnapshot, queuedSnapshot);
    });
  }

  recordUserInteraction(): void {
    this.lastInteractionAtMs = this.now();
  }

  /** Dismisses the current bubble while leaving consent and observation state unchanged. */
  dismissBubble(): void {
    this.recordUserInteraction();
    this.bubbles.dismiss();
  }

  /** Pauses an enabled session when Windows makes the primary screen unavailable. */
  suspend(message: string): Promise<void> {
    if (!this.options.getEnabled() || this.status === "paused") return Promise.resolve();
    return this.pause(message);
  }

  /** Resumes a paused persistent session without capturing a frame immediately. */
  resume(): Promise<void> {
    const intent = ++this.lifecycleIntent;
    return this.enqueueLifecycle(async () => {
      if (
        intent !== this.lifecycleIntent
        || !this.options.getEnabled()
        || this.sessionId
        || (this.status !== "paused" && this.status !== "failed")
      ) return;
      const roleId = this.options.getRoleId();
      if (!roleId || !this.options.pet.isRunning) return;
      this.startSession(roleId);
    });
  }

  requestObservation(): Promise<void> {
    if (!this.options.getEnabled()) return Promise.resolve();
    const roleId = this.options.getRoleId();
    if (!roleId || !this.options.pet.isRunning) {
      return this.pause("桌宠不可用，屏幕观察已暂停");
    }
    if (!this.sessionId || this.sessionRoleId !== roleId) {
      const intent = this.lifecycleIntent;
      const snapshot = this.invalidateSession();
      return this.enqueueLifecycle(async () => {
        await this.settleSnapshot(snapshot);
        if (intent !== this.lifecycleIntent || !this.options.getEnabled()) return;
        const currentRoleId = this.options.getRoleId();
        if (!currentRoleId || !this.options.pet.isRunning) return;
        if (!this.sessionId || this.sessionRoleId !== currentRoleId) {
          this.startSession(currentRoleId);
        }
        await this.requestObservation();
      });
    }
    const generation = this.generation;
    if (this.activeRequest?.generation === generation) return this.activeRequest.promise;

    const request: ActiveObservationRequest = {
      generation,
      promise: Promise.resolve(),
    };
    request.promise = this.runObservation(generation, roleId).finally(() => {
      if (this.activeRequest === request) this.activeRequest = null;
    });
    this.activeRequest = request;
    return request.promise;
  }

  private async runObservation(generation: number, roleId: string): Promise<void> {
    if (!this.isCurrentSession(generation, roleId)) return;
    this.publish("reviewing");
    try {
      const result = await requestObservationResult({
        bridge: this.options.bridge,
        roleId,
        captureFrame: this.options.captureFrame,
        previousResult: this.latestResult,
        recentBubbles: this.bubbles.recent.slice(),
        isCurrent: () => this.isCurrentSession(generation, roleId),
      });
      if (!result) return;
      this.latestResult = result;
      this.lastObservationAtMs = this.now();
      await this.acceptExperience(result, roleId, this.sessionId);
      if (!this.isCurrentSession(generation, roleId)) return;
      this.publish("observing", this.bubbles.accept(result.bubble), false);
    } catch (error) {
      if (!this.isCurrentSession(generation, roleId)) return;
      this.clearEphemera();
      if (error instanceof PrimaryDisplayUnavailableError) {
        await this.pause("主屏幕暂时不可用，屏幕观察已暂停");
        return;
      }
      this.publish("failed", "屏幕观察失败，请稍后重试", true);
    }
  }

  private startSession(roleId: string): void {
    this.sessionId = randomUUID();
    this.sessionRoleId = roleId;
    this.episodeIndex = 0;
    this.lastObservationAtMs = 0;
    this.lastInteractionAtMs = this.now();
    this.publish("observing");
    this.scheduler.start();
  }

  private async acceptExperience(
    result: ObservationResult,
    roleId: string,
    sessionId: string,
  ): Promise<void> {
    const transition = reduceObservationEpisode(this.episode, result, this.episodeIndex);
    this.episode = transition.current;
    if (transition.settled) this.bubbles.resetEpisode();
    if (transition.current && transition.current.index === this.episodeIndex) this.episodeIndex += 1;
    if (transition.settled) await this.rememberEpisode(transition.settled, roleId, sessionId);
  }

  private async settleSnapshot(snapshot: ObservationSessionSnapshot): Promise<void> {
    if (snapshot.episode) {
      await this.rememberEpisode(snapshot.episode, snapshot.roleId, snapshot.sessionId);
    }
  }

  private async settleSnapshots(...snapshots: ObservationSessionSnapshot[]): Promise<void> {
    for (const snapshot of snapshots) await this.settleSnapshot(snapshot);
  }

  private async rememberEpisode(
    episode: ObservationEpisode,
    roleId: string,
    sessionId: string,
  ): Promise<void> {
    if (!roleId || !sessionId || !episode.summary.trim()) return;
    const response = await this.options.bridge.invoke({
      method: "observation.remember",
      payload: {
        role_id: roleId,
        summary: episode.summary,
        happened_at: episode.happenedAt,
        source_ref: `desktop-observation:${sessionId}:${episode.index}`,
      },
    });
    if (response.error) throw new Error(response.error.message);
  }

  private async pause(message: string): Promise<void> {
    const intent = ++this.lifecycleIntent;
    const immediateSnapshot = this.invalidateSession();
    this.publish("paused", message, true, true);
    return this.enqueueLifecycle(async () => {
      const queuedSnapshot = this.invalidateSession();
      if (intent === this.lifecycleIntent) this.publish("paused", message, true, true);
      try {
        await this.settleSnapshots(immediateSnapshot, queuedSnapshot);
      } catch (error) {
        if (intent === this.lifecycleIntent) {
          this.publish("failed", "观察经历保存失败", true, true);
        }
        throw error;
      }
    });
  }

  private invalidateSession(): ObservationSessionSnapshot {
    const snapshot = {
      roleId: this.sessionRoleId,
      sessionId: this.sessionId,
      episode: this.episode,
    };
    this.generation += 1;
    this.scheduler.stop();
    this.clearEphemera();
    this.sessionId = "";
    this.sessionRoleId = "";
    this.episode = null;
    return snapshot;
  }

  private isCurrentSession(generation: number, roleId: string): boolean {
    return generation === this.generation
      && roleId === this.sessionRoleId
      && Boolean(this.sessionId)
      && this.options.getEnabled();
  }

  private clearEphemera(): void {
    this.latestResult = null;
    this.bubbles.clear();
  }

  private requestDetachedObservation(): void {
    void this.requestObservation().catch((error) => {
      this.options.onError?.(error);
    });
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

  private enqueueLifecycle(operation: () => Promise<void>): Promise<void> {
    const next = this.lifecycleQueue.then(operation, operation);
    this.lifecycleQueue = next.catch(() => undefined);
    return next;
  }
}
