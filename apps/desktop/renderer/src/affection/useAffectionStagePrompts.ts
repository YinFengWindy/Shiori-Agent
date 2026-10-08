import { SerialDraftQueue, autosaveDebounceMs, errorFeedback, errorFeedbackText } from "@yinfengwindy/shiori-sdk/host-internal";
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
import {
  changedStagePrompts,
  stagePromptRequest,
  stagePromptRows,
  stagePromptTexts,
  type StagePromptTexts,
} from "./stagePromptSelectors";

type Loaded = { stages: AffectionStagePrompt[]; texts: StagePromptTexts };

const sameRequest = (a: AffectionStagePromptChanges | null, b: AffectionStagePromptChanges | null) =>
  a !== null && b !== null && JSON.stringify(a) === JSON.stringify(b);

const savedRequest = (stages: AffectionStagePrompt[]) => stagePromptRequest(stages, stagePromptTexts(stages));

/**
 * The save queue plus this editor's baseline in request form: what it loaded,
 * then what it last submitted successfully. Each attempt writes only the
 * stages this editor changed since, so stages changed elsewhere survive; the
 * server's answer never becomes the baseline, since the fields still show
 * this editor's own texts for those stages.
 */
function createStagePromptAutosave(
  write: (changes: AffectionStagePromptChanges) => Promise<AffectionStagePrompts>,
  onStatus: (phase: DraftSavePhase, message: string) => void,
) {
  let saved: AffectionStagePromptChanges = {};
  const queue = new SerialDraftQueue<AffectionStagePromptChanges, AffectionStagePrompts>({
    debounceMs: autosaveDebounceMs,
    isEqual: sameRequest,
    clone: (request) => ({ ...request }),
    attempt: async (request) => {
      try {
        return { ok: true, result: await write(changedStagePrompts(request, saved)) };
      } catch (error) {
        return { ok: false, resumesAutomatically: false, ...errorFeedback(error, "保存失败") };
      }
    },
    onApplied: (_result, submitted) => { saved = { ...submitted }; },
    onStatus,
  });
  return {
    queue,
    get saved() { return saved; },
    /** Takes a fresh read as the baseline. */
    adopt(stages: AffectionStagePrompt[]) { saved = savedRequest(stages); },
  };
}

/**
 * Loads a role's stage guidance and autosaves the edited fields through the
 * shared `SerialDraftQueue`: a run of edits saves once they pause, restoring a
 * default saves at once, and unmounting submits the last edit. Each save
 * writes only the stages this editor changed since its last save, so edits made
 * elsewhere to other stages survive. The fields keep what was typed. The
 * editor is keyed by role, so one hook instance serves one role.
 */
export function useAffectionStagePrompts(invoke: DesktopInvoke, roleId: string) {
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [loadError, setLoadError] = useState("");
  const [reloads, setReloads] = useState(0);
  const [save, setSave] = useState<{ phase: DraftSavePhase; error: string }>({ phase: "idle", error: "" });
  // The queue outlives renders; its writes go through the latest invoke.
  const target = useLatestRef({ invoke, roleId });
  const [autosave] = useState(() => createStagePromptAutosave(
    (changes) => writeAffectionStagePrompts(target.current.invoke, target.current.roleId, changes),
    (phase, message) => setSave({ phase, error: phase === "idle" || phase === "saving" ? "" : message }),
  ));
  const { queue } = autosave;

  useEffect(() => {
    let cancelled = false;
    readAffectionStagePrompts(invoke, roleId).then((answer) => {
      if (cancelled) return;
      autosave.adopt(answer.stages);
      setLoaded({ stages: answer.stages, texts: stagePromptTexts(answer.stages) });
      setLoadError("");
    }, (error: unknown) => {
      if (!cancelled) setLoadError(errorFeedbackText(error));
    });
    return () => { cancelled = true; };
  }, [autosave, invoke, roleId, reloads]);
  useEffect(() => () => queue.flush(), [queue]);

  function edit(stage: string, text: string) {
    if (!loaded) return;
    const texts = { ...loaded.texts, [stage]: text };
    setLoaded({ ...loaded, texts });
    queue.enqueue(stagePromptRequest(loaded.stages, texts), autosave.saved);
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
