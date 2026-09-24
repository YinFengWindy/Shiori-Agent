import { failureFromReadiness, type GenerationFailure } from "./generationFailure";
import type { NovelAiPageState } from "./novelAiPageStore";
import type { ImageHistoryRecord, ImageSizePreset, ImageStudioFormState } from "./types";

/** What the canvas shows, in priority order: work in flight, a failure, a picture, or nothing yet. */
export type StageView =
  | { kind: "generating"; aspect: number }
  | { kind: "failure"; failure: GenerationFailure }
  | {
    kind: "image";
    path: string;
    record: ImageHistoryRecord | null;
    /** Freshly generated: plays the reveal motion. */
    reveal: boolean;
    /** A standing problem (token not configured) shown above the picture. */
    notice: GenerationFailure | null;
  }
  | { kind: "empty" };

const presetSize: Record<Exclude<ImageSizePreset, "custom">, [number, number]> = {
  square: [1024, 1024],
  landscape: [1216, 832],
  portrait: [832, 1216],
};

/** The dimensions a size preset stands for; custom sizes fall back to square until both sides are valid. */
export function resolvePresetSize(form: Pick<ImageStudioFormState, "sizePreset" | "customWidth" | "customHeight">): [number, number] {
  if (form.sizePreset !== "custom") return presetSize[form.sizePreset];
  const width = Number(form.customWidth);
  const height = Number(form.customHeight);
  return width > 0 && height > 0 ? [width, height] : presetSize.square;
}

/**
 * The history record the canvas should show: the explicit selection, else
 * the most recent.
 */
export function selectActiveHistoryRecord(
  history: ImageHistoryRecord[],
  selectedRecordId: string,
): ImageHistoryRecord | null {
  return history.find((item) => item.id === selectedRecordId) ?? history[0] ?? null;
}

/** Derives the canvas state from the shared page state. */
export function selectStageView(state: Pick<NovelAiPageState,
  "submitting" | "failure" | "history" | "selectedRecordId" | "latestResult" | "revealRecordId" | "readiness" | "form">): StageView {
  if (state.submitting) {
    const [width, height] = resolvePresetSize(state.form);
    return { kind: "generating", aspect: width / height };
  }
  if (state.failure) return { kind: "failure", failure: state.failure };
  const listed = selectActiveHistoryRecord(state.history, state.selectedRecordId);
  // A result selected before the history refresh lists it must not flash the previous picture.
  const pending = state.latestResult && state.latestResult.record_id === state.selectedRecordId && listed?.id !== state.selectedRecordId
    ? state.latestResult
    : null;
  const record = pending ? null : listed;
  const path = pending?.output_paths[0] ?? record?.output_paths[0] ?? state.latestResult?.output_paths[0] ?? "";
  const notConfigured = failureFromReadiness(state.readiness);
  if (path) {
    const shownId = pending?.record_id ?? record?.id ?? state.latestResult?.record_id ?? "";
    return {
      kind: "image",
      path,
      record,
      reveal: Boolean(state.revealRecordId) && shownId === state.revealRecordId,
      notice: notConfigured,
    };
  }
  if (notConfigured) return { kind: "failure", failure: notConfigured };
  return { kind: "empty" };
}

/** Whether generation is blocked by a known-unusable token (unknown readiness does not block). */
export function selectGenerationBlocked(readiness: NovelAiPageState["readiness"]): boolean {
  return readiness?.configured === false;
}
