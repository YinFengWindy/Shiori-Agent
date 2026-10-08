import { cardClass, compactButtonSizeClass, cx, ghostButtonSurfaceClass, textareaClass } from "@yinfengwindy/shiori-sdk";
import type { DesktopInvoke } from "../shared/bridgeInvoke";
import { InlineError } from "../shared/feedback/InlineError";
import { ReadError, ReadStatusLine, readStatusText } from "../shared/feedback/ReadStatus";
import { compactTextButtonClass } from "../shared/styles";
import { SettingsSavedIndicator } from "../settings/SettingsSavedIndicator";
import type { StagePromptRow } from "./stagePromptSelectors";
import { useAffectionStagePrompts } from "./useAffectionStagePrompts";

/** One stage's guidance field, with 「恢复默认」 while it differs from the default. */
function StagePromptField({ row, onEdit, onRestore }: {
  row: StagePromptRow;
  onEdit: (text: string) => void;
  onRestore: () => void;
}) {
  const fieldId = `affection-stage-prompt-${row.stage}`;
  return <div className="grid gap-1.5" data-testid="affection-stage-prompt">
    <div className="flex min-h-9 items-center justify-between gap-2">
      <label htmlFor={fieldId} className="text-body-sm font-medium text-ink-secondary">{row.stage}</label>
      {row.overridden && <button type="button" className={compactTextButtonClass} onClick={onRestore}>恢复默认</button>}
    </div>
    <textarea id={fieldId} className={textareaClass} rows={3} value={row.text} onChange={(event) => onEdit(event.target.value)} />
  </div>;
}

/** The 「好感度」 tab's per-stage guidance, autosaved as it is edited. */
export function AffectionStagePromptEditor({ invoke, roleId }: { invoke: DesktopInvoke; roleId: string }) {
  const prompts = useAffectionStagePrompts(invoke, roleId);
  if (prompts.loadError) return <ReadError error={prompts.loadError} onRetry={prompts.reload} />;
  if (!prompts.rows) return <ReadStatusLine text={readStatusText.loading} />;
  return <section className={cx(cardClass, "grid gap-4 px-5 py-4")} aria-label="阶段语气" data-testid="affection-stage-prompts">
    <div className="flex items-center justify-between gap-3">
      <h3 className="m-0 font-display text-title-sm text-ink">阶段语气</h3>
      <SettingsSavedIndicator phase={prompts.savePhase} showPending />
    </div>
    {prompts.saveError && <InlineError
      message={prompts.saveError}
      actions={<button type="button" className={cx(ghostButtonSurfaceClass, compactButtonSizeClass)} onClick={prompts.retrySave}>重试</button>}
    />}
    {prompts.rows.map((row) => <StagePromptField key={row.stage} row={row}
      onEdit={(text) => prompts.edit(row.stage, text)} onRestore={() => prompts.restore(row.stage)} />)}
  </section>;
}
