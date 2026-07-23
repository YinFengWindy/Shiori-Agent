import type { ObservationStatus, PetObservationPayload } from "./types.js";

const defaultBubbleDurationMs = 5_000;
const recentBubbleLimit = 3;

/** Owns safe bubble visibility, expiry, and per-episode repetition suppression. */
export class ObservationBubbleController {
  private timer: ReturnType<typeof setTimeout> | null = null;
  private payload: PetObservationPayload = {
    status: "off",
    enabled: false,
    bubble: "",
    persistent: false,
  };
  private recentBubbles: string[] = [];

  constructor(
    private readonly emit: (payload: PetObservationPayload) => void,
    private readonly durationMs = defaultBubbleDurationMs,
  ) {}

  get recent(): readonly string[] {
    return this.recentBubbles;
  }

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

  republish(status: ObservationStatus, enabled: boolean): void {
    this.publish(status, enabled, this.payload.bubble, this.payload.persistent);
  }

  dismiss(): void {
    if (!this.payload.bubble) return;
    this.publish(this.payload.status, this.payload.enabled);
  }

  accept(candidate: string): string {
    const bubble = candidate.trim();
    if (!bubble || isRepetitiveObservationBubble(bubble, this.recentBubbles)) return "";
    this.recentBubbles.push(bubble);
    if (this.recentBubbles.length > recentBubbleLimit) this.recentBubbles.shift();
    return bubble;
  }

  resetEpisode(): void {
    this.recentBubbles = [];
  }

  clear(): void {
    this.clearTimer();
    this.recentBubbles = [];
    this.payload = { ...this.payload, bubble: "", persistent: false };
  }

  private clearTimer(): void {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
  }
}

/** Rejects exact and near-identical bubble wording within one experience episode. */
export function isRepetitiveObservationBubble(candidate: string, recent: readonly string[]): boolean {
  const normalized = normalizeBubble(candidate);
  if (!normalized) return true;
  return recent.some((item) => {
    const previous = normalizeBubble(item);
    if (normalized === previous) return true;
    if (Math.min(normalized.length, previous.length) >= 6) {
      if (normalized.includes(previous) || previous.includes(normalized)) return true;
      return diceSimilarity(normalized, previous) >= 0.82;
    }
    return false;
  });
}

function normalizeBubble(value: string): string {
  return value.toLocaleLowerCase().replace(/[\p{P}\p{S}\s]+/gu, "");
}

function diceSimilarity(left: string, right: string): number {
  const leftPairs = characterPairs(left);
  const rightPairs = characterPairs(right);
  if (!leftPairs.size || !rightPairs.size) return 0;
  let overlap = 0;
  for (const pair of leftPairs) {
    if (rightPairs.has(pair)) overlap += 1;
  }
  return (2 * overlap) / (leftPairs.size + rightPairs.size);
}

function characterPairs(value: string): Set<string> {
  const pairs = new Set<string>();
  for (let index = 0; index < value.length - 1; index += 1) {
    pairs.add(value.slice(index, index + 2));
  }
  return pairs;
}
