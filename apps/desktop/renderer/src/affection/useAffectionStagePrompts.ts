import { SerialDraftQueue, errorFeedback, errorFeedbackText } from "@yinfengwindy/shiori-sdk/host-internal";
import { useEffect, useState } from "react";
import { useLatestRef, type DraftSavePhase } from "@yinfengwindy/shiori-sdk";
import type { DesktopInvoke } from "../shared/bridgeInvoke";
import {
  readAffectionStagePrompts,
  writeAffectionStagePrompts,
  type AffectionStagePrompt,
  type AffectionStagePromptChanges,
  type AffectionStagePrompts,
} from "./affectionStagePrompts";
import { stagePromptRequest, stagePromptRows, stagePromptTexts, type StagePromptTexts } from "./stagePromptSelectors";

/** Quiet period merging a run of keystrokes into one save, as on the host's other autosaved pages. */
const autosaveDebounceMs = 400;

type Loaded = {
  stages: AffectionStagePrompt[];
  /** The stored overrides, in request form. */
  saved: AffectionStagePromptChanges;
  texts: StagePromptTexts;
};

const sameRequest = (a: AffectionStagePromptChanges | null, b: AffectionStagePromptChanges | null) =>
  a !== null && b !== null && JSON.stringify(a) === JSON.stringify(b);

const savedRequest = (stages: AffectionStagePrompt[]) => stagePromptRequest(stages, stagePromptTexts(stages));

/**
 * Loads a role's stage guidance and autosaves the edited fields through the
 * shared `SerialDraftQueue`: a run of edits saves once they pause, restoring a
 * default saves at once, and unmounting submits the last edit. The fields
 * keep what was typed; a save only refreshes what is stored. The editor is
 * keyed by role, so one hook instance serves one role.
 */
export function useAffectionStagePrompts(invoke: DesktopInvoke, roleId: string) {
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [loadError, setLoadError] = useState("");
  const [reloads, setReloads] = useState(0);
  const [save, setSave] = useState<{ phase: DraftSavePhase; error: string }>({ phase: "idle", error: "" });
  // The queue outlives renders; its writes go through the latest invoke.
  const target = useLatestRef({ invoke, roleId });

  const [queue] = useState(() => new SerialDraftQueue<AffectionStagePromptChanges, AffectionStagePrompts>({
    debounceMs: autosaveDebounceMs,
    isEqual: sameRequest,
    clone: (request) => ({ ...request }),
    attempt: async (request) => {
      try {
        return { ok: true, result: await writeAffectionStagePrompts(target.current.invoke, target.current.roleId, request) };
      } catch (error) {
        return { ok: false, resumesAutomatically: false, ...errorFeedback(error, "保存失败") };
      }
    },
    onApplied: (result) => setLoaded((current) => current && { ...current, stages: result.stages, saved: savedRequest(result.stages) }),
    onStatus: (phase, message) => setSave({ phase, error: phase === "idle" || phase === "saving" ? "" : message }),
  }));

  useEffect(() => {
    let cancelled = false;
    readAffectionStagePrompts(invoke, roleId).then((answer) => {
      if (cancelled) return;
      setLoaded({ stages: answer.stages, saved: savedRequest(answer.stages), texts: stagePromptTexts(answer.stages) });
      setLoadError("");
    }, (error: unknown) => {
      if (!cancelled) setLoadError(errorFeedbackText(error));
    });
    return () => { cancelled = true; };
  }, [invoke, roleId, reloads]);
  useEffect(() => () => queue.flush(), [queue]);

  function edit(stage: string, text: string) {
    if (!loaded) return;
    const texts = { ...loaded.texts, [stage]: text };
    setLoaded({ ...loaded, texts });
    queue.enqueue(stagePromptRequest(loaded.stages, texts), loaded.saved);
  }

  return {
    /** The fields in stage order; null until the first read answers. */
    rows: loaded ? stagePromptRows(loaded.stages, loaded.texts) : null,
    loadError,
    reload: () => setReloads((count) => count + 1),
    savePhase: save.phase,
    saveError: save.error,
    retrySave: () => queue.retry(),
    /** Edits one stage's text; saved once edits pause. */
    edit,
    /** Puts the stage back to its default text and saves at once. */
    restore(stage: string) {
      const item = loaded?.stages.find((candidate) => candidate.stage === stage);
      if (!item) return;
      edit(stage, item.default);
      queue.flush();
    },
  };
}
