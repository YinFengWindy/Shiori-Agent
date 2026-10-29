import { useRef } from "react";
import { usePrivateAutosave, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import {
  readAffectionStagePrompts,
  writeAffectionStagePrompts,
  type AffectionStagePrompt,
  type AffectionStagePromptChanges,
} from "./affectionStagePrompts";
import {
  changedStagePrompts,
  stagePromptRequest,
  stagePromptRows,
  stagePromptTexts,
  type StagePromptTexts,
} from "./stagePromptSelectors";

type StagePromptDocument = { stages: AffectionStagePrompt[]; texts: StagePromptTexts };

/**
 * Loads a role's stage guidance and autosaves edited fields. Each save writes
 * only the stages this editor changed since its own baseline, so stages
 * changed elsewhere survive. The fields keep what was typed.
 */
export function useAffectionStagePrompts(client: PluginRpcClient, roleId: string) {
  const baseline = useRef<AffectionStagePromptChanges>({});
  const autosave = usePrivateAutosave<StagePromptDocument>(client, roleId, {
    async load() {
      const page = await readAffectionStagePrompts(client, roleId);
      const texts = stagePromptTexts(page.stages);
      baseline.current = stagePromptRequest(page.stages, texts);
      return { stages: page.stages, texts };
    },
    async save(value) {
      const request = stagePromptRequest(value.stages, value.texts);
      const changes = changedStagePrompts(request, baseline.current);
      if (Object.keys(changes).length > 0) await writeAffectionStagePrompts(client, roleId, changes);
      baseline.current = request;
      return value;
    },
  });
  const draft = autosave.draft;

  return {
    /** The fields in stage order; null until the first read answers. */
    rows: draft ? stagePromptRows(draft.stages, draft.texts) : null,
    loadError: autosave.loadError,
    reload: autosave.reload,
    savePhase: autosave.savePhase,
    saveError: autosave.saveError,
    retrySave: autosave.retry,
    /** Edits one stage's text; saved once edits pause. */
    edit(stage: string, text: string) {
      autosave.update((current) => ({ ...current, texts: { ...current.texts, [stage]: text } }));
    },
    /** Puts the stage back to its default text and saves at once. */
    restore(stage: string) {
      const item = draft?.stages.find((candidate) => candidate.stage === stage);
      if (!item) return;
      autosave.commit((current) => ({ ...current, texts: { ...current.texts, [stage]: item.default } }));
    },
  };
}
