import { useId, useState } from "react";
import { compactButtonSizeClass, cx, ghostButtonSurfaceClass, textareaClass } from "@yinfengwindy/shiori-sdk";
import type { DesktopInvoke } from "../shared/bridgeInvoke";
import { InlineError } from "../shared/feedback/InlineError";
import { ReadError, ReadStatusLine, readStatusText } from "../shared/feedback/ReadStatus";
import { compactTextButtonClass, segmentedTabClass, segmentedTabListClass } from "../shared/styles";
import { SettingsSavedIndicator } from "../settings/SettingsSavedIndicator";
import { AffectionCard } from "./AffectionCard";
import { neutralAffectionStage } from "./affectionStages";
import { selectedStagePromptRow, type StagePromptRow } from "./stagePromptSelectors";
import { useAffectionStagePrompts } from "./useAffectionStagePrompts";

/** The stage switcher: one segment per stage, marked while its text differs from the default. */
function StageTabs({ rows, selected, idPrefix, onSelect }: {
  rows: readonly StagePromptRow[];
  selected: string;
  idPrefix: string;
  onSelect: (stage: string) => void;
}) {
  return <div role="tablist" aria-label="阶段" className={cx(segmentedTabListClass, "flex flex-wrap gap-1 justify-self-start")}>
    {rows.map((row) => <button
      key={row.stage}
      type="button"
      role="tab"
      id={`${idPrefix}-tab-${row.stage}`}
      aria-selected={row.stage === selected}
      aria-controls={`${idPrefix}-panel`}
      className={cx(segmentedTabClass(row.stage === selected), "inline-flex items-center gap-1.5")}
      onClick={() => onSelect(row.stage)}
    >
      {row.stage}
      {row.overridden && <span role="img" aria-label="已自定义" className="h-1.5 w-1.5 rounded-full bg-accent" data-testid="affection-stage-customized" />}
    </button>)}
  </div>;
}

/** The selected stage's guidance field, with 「恢复默认」 while it differs from the default. */
function StagePromptField({ row, idPrefix, onEdit, onRestore }: {
  row: StagePromptRow;
  idPrefix: string;
  onEdit: (text: string) => void;
  onRestore: () => void;
}) {
  return <div role="tabpanel" id={`${idPrefix}-panel`} aria-labelledby={`${idPrefix}-tab-${row.stage}`} className="grid gap-2" data-testid="affection-stage-prompt">
    <textarea className={textareaClass} rows={4} aria-label={row.stage} value={row.text} onChange={(event) => onEdit(event.target.value)} />
    <div className="flex min-h-8 items-center justify-end">
      {row.overridden && <button type="button" className={compactTextButtonClass} onClick={onRestore}>恢复默认</button>}
    </div>
  </div>;
}

type AffectionStagePromptEditorProps = {
  invoke: DesktopInvoke;
  roleId: string;
  /**
   * The role's current stage, followed until a tab is clicked or a field edited (then the
   * selection stays put, so a late answer never swaps a field being typed in); null before
   * initialization or while unknown, which shows 「陌生」.
   */
  currentStage?: string | null;
};

/**
 * The 「阶段语气」 card: one stage's guidance at a time, autosaved as it is
 * edited. Every stage's text lives in the hook, so switching stages keeps
 * unsaved edits.
 */
export function AffectionStagePromptEditor({ invoke, roleId, currentStage = null }: AffectionStagePromptEditorProps) {
  const prompts = useAffectionStagePrompts(invoke, roleId);
  const [picked, setPicked] = useState<string | null>(null);
  const idPrefix = useId();
  const row = prompts.rows ? selectedStagePromptRow(prompts.rows, picked, currentStage ?? neutralAffectionStage) : undefined;
  return <AffectionCard title="阶段语气" testId="affection-stage-prompts" aside={<SettingsSavedIndicator phase={prompts.savePhase} showPending />}>
    {prompts.loadError && <ReadError error={prompts.loadError} onRetry={prompts.reload} />}
    {!prompts.loadError && !prompts.rows && <ReadStatusLine text={readStatusText.loading} />}
    {prompts.saveError && <InlineError
      message={prompts.saveError}
      actions={<button type="button" className={cx(ghostButtonSurfaceClass, compactButtonSizeClass)} onClick={prompts.retrySave}>重试</button>}
    />}
    {!prompts.loadError && prompts.rows && row && <>
      <StageTabs rows={prompts.rows} selected={row.stage} idPrefix={idPrefix} onSelect={setPicked} />
      <StagePromptField key={row.stage} row={row} idPrefix={idPrefix}
        onEdit={(text) => { setPicked(row.stage); prompts.edit(row.stage, text); }}
        onRestore={() => { setPicked(row.stage); prompts.restore(row.stage); }} />
    </>}
  </AffectionCard>;
}
