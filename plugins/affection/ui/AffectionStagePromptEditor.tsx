import { useId, useState } from "react";
import {
  badgeClass,
  compactButtonSizeClass,
  compactGhostButtonClass,
  cx,
  ghostButtonSurfaceClass,
  textareaClass,
  type PluginHostServices,
  type PluginRpcClient,
} from "@yinfengwindy/shiori-sdk";
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
  return <div role="tablist" aria-label="阶段" className="flex flex-wrap gap-1 justify-self-start rounded-md bg-surface-soft p-1">
    {rows.map((row) => <button
      key={row.stage}
      type="button"
      role="tab"
      id={`${idPrefix}-tab-${row.stage}`}
      aria-selected={row.stage === selected}
      aria-controls={`${idPrefix}-panel`}
      className={cx(
        "inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md px-3 text-body-sm transition-colors",
        row.stage === selected ? badgeClass : "text-ink-muted hover:text-ink",
      )}
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
      {row.overridden && <button type="button" className={compactGhostButtonClass} onClick={onRestore}>恢复默认</button>}
    </div>
  </div>;
}

type AffectionStagePromptEditorProps = {
  client: PluginRpcClient;
  host: PluginHostServices;
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
export function AffectionStagePromptEditor({ client, host, roleId, currentStage = null }: AffectionStagePromptEditorProps) {
  const prompts = useAffectionStagePrompts(client, roleId);
  const [picked, setPicked] = useState<string | null>(null);
  const idPrefix = useId();
  const row = prompts.rows ? selectedStagePromptRow(prompts.rows, picked, currentStage ?? neutralAffectionStage) : undefined;
  const { InlineError, SettingsSavedStatus } = host.ui;
  return <AffectionCard title="阶段语气" testId="affection-stage-prompts" aside={<SettingsSavedStatus phase={prompts.savePhase} />}>
    {prompts.loadError && <InlineError message={prompts.loadError} actions={<button type="button" className={cx(ghostButtonSurfaceClass, compactButtonSizeClass)} onClick={prompts.reload}>重试</button>} />}
    {!prompts.loadError && !prompts.rows && <p className="m-0 text-body-sm text-ink-muted">加载中…</p>}
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
