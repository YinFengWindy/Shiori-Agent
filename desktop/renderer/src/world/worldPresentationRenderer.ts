import type { PerformancePlan, PresentationCue } from "./presentationProtocol";
import type { WorldAssetManifestEntry } from "./worldAssetManager";

export type WorldPresentationPrepareRequest = {
  plan: PerformancePlan;
  manifest: readonly WorldAssetManifestEntry[];
  initialAssetId?: string;
  fallbackText: string;
};

/** Rendering boundary shared by the Pixi stage and its text-only fallback. */
export interface WorldPresentationRenderer {
  readonly kind: "pixi" | "text";
  initialize(host: HTMLElement): Promise<void>;
  prepare(request: WorldPresentationPrepareRequest, signal?: AbortSignal): Promise<void>;
  recover(cues: readonly PresentationCue[], signal?: AbortSignal): Promise<void>;
  render(cue: PresentationCue, signal?: AbortSignal): Promise<void>;
  pause(): void;
  resume(): void;
  skip(): void;
  dispose(): void;
}

export type TextPresentationSnapshot = {
  text: string;
  cueId: string | null;
};

function cueText(cue: PresentationCue): string {
  const value = cue.payload.content ?? cue.payload.text;
  return typeof value === "string" && value.trim() ? value : "";
}

/** Maintains readable narrative state when graphical presentation is unavailable. */
export class TextWorldPresentationRenderer implements WorldPresentationRenderer {
  readonly kind = "text" as const;
  #snapshot: TextPresentationSnapshot = { text: "", cueId: null };
  #onChange: (snapshot: TextPresentationSnapshot) => void;
  #disposed = false;

  constructor(onChange: (snapshot: TextPresentationSnapshot) => void = () => undefined) {
    this.#onChange = onChange;
  }

  async initialize(): Promise<void> {
    this.#assertActive();
  }

  async prepare(request: WorldPresentationPrepareRequest): Promise<void> {
    this.#assertActive();
    this.#publish({ text: request.fallbackText, cueId: null });
  }

  async recover(cues: readonly PresentationCue[]): Promise<void> {
    for (const cue of cues) await this.render(cue);
  }

  async render(cue: PresentationCue): Promise<void> {
    this.#assertActive();
    const text = cueText(cue);
    if (text) this.#publish({ text, cueId: cue.cueId });
  }

  pause(): void {}

  resume(): void {}

  skip(): void {}

  dispose(): void {
    this.#disposed = true;
    this.#onChange = () => undefined;
  }

  snapshot(): TextPresentationSnapshot {
    return { ...this.#snapshot };
  }

  #publish(snapshot: TextPresentationSnapshot): void {
    this.#snapshot = snapshot;
    this.#onChange(this.snapshot());
  }

  #assertActive(): void {
    if (this.#disposed) throw new Error("text presentation renderer is disposed");
  }
}

/** Runs one plan in order while keeping persistence checkpoints outside renderers. */
export async function playPresentationPlan(
  renderer: WorldPresentationRenderer,
  request: WorldPresentationPrepareRequest,
  options: {
    signal?: AbortSignal;
    startCueIndex?: number;
    onCueComplete?: (cue: PresentationCue) => Promise<void> | void;
  } = {},
): Promise<void> {
  await renderer.prepare(request, options.signal);
  const startCueIndex = Math.min(
    request.plan.cues.length,
    Math.max(0, options.startCueIndex ?? 0),
  );
  await renderer.recover(request.plan.cues.slice(0, startCueIndex), options.signal);
  for (const [index, cue] of request.plan.cues.entries()) {
    if (index < startCueIndex) continue;
    if (options.signal?.aborted) {
      throw options.signal.reason ?? new DOMException("Aborted", "AbortError");
    }
    await renderer.render(cue, options.signal);
    if (cue.checkpoint || index === request.plan.cues.length - 1) {
      await options.onCueComplete?.(cue);
    }
  }
}

function assetKindForCue(cue: PresentationCue): WorldAssetManifestEntry["kind"] | null {
  if (cue.kind === "background") return "background";
  if (cue.kind === "sprites") return "character";
  if (cue.kind === "cg") return "cg";
  return null;
}

/** Extracts explicit opaque asset references without interpreting bridge paths in PixiJS. */
export function createWorldAssetManifest(plan: PerformancePlan): WorldAssetManifestEntry[] {
  const entries = new Map<string, WorldAssetManifestEntry>();
  for (const cue of plan.cues) {
    const kind = assetKindForCue(cue);
    if (!kind) continue;
    const visit = (value: unknown): void => {
      if (Array.isArray(value)) {
        value.forEach(visit);
        return;
      }
      if (typeof value !== "object" || value === null) return;
      const record = value as Record<string, unknown>;
      const url = [record.assetUrl, record.imageUrl, record.url]
        .find((candidate): candidate is string => typeof candidate === "string" && candidate.startsWith("shiori-asset://"));
      const id = [record.assetId, record.id, record.asset]
        .find((candidate): candidate is string => typeof candidate === "string" && Boolean(candidate.trim()));
      if (url && id) {
        const fallbackIds = Array.isArray(record.fallbackIds)
          ? record.fallbackIds.filter((candidate): candidate is string => typeof candidate === "string")
          : undefined;
        entries.set(id, { id, url, kind, fallbackIds });
      }
      Object.values(record).forEach(visit);
    };
    visit(cue.payload);
  }
  return [...entries.values()];
}
