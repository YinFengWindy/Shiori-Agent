import { inputClass } from "@shiori/plugin-sdk";
import { InlineError } from "../shared/feedback/InlineError";
import { compactPrimaryButtonClass, compactTextButtonClass } from "../shared/styles";
import { useBusyAction } from "../shared/useBusyAction";
import { useEditDraft } from "../shared/useEditDraft";
import { dailyCapDraftDirty, parseDailyCap } from "./phoneListening";

/**
 * A daily listening cap field, saved or reverted while it differs from
 * `stored`. With `allowBlank` an empty field saves null (the default,
 * shown as the placeholder, applies); otherwise a number is required.
 */
export function PhoneDailyCapField({ stored, label, placeholder, allowBlank = false, testId, onSave }: {
  stored: number | null;
  label: string;
  placeholder?: string;
  allowBlank?: boolean;
  testId: string;
  onSave: (dailyCap: number | null) => Promise<void>;
}) {
  const { draft, dirty, setDraft, reset } = useEditDraft(stored === null ? "" : String(stored), dailyCapDraftDirty);
  const saving = useBusyAction();
  const parsed = parseDailyCap(draft);
  const valid = parsed !== undefined && (allowBlank || parsed !== null);
  return (
    <div className="grid gap-1.5">
      <label className="flex min-w-0 items-center gap-2 px-0.5 text-caption text-ink-muted">
        <span className="shrink-0">{label}</span>
        <input className={inputClass} inputMode="numeric" value={draft} placeholder={placeholder} aria-invalid={!valid}
          disabled={saving.busy} data-testid={testId} onChange={(event) => setDraft(event.target.value)} />
      </label>
      {!valid ? <p className="m-0 px-0.5 text-caption text-danger-text">至少为 1 的整数</p> : null}
      {saving.error ? <InlineError message={saving.error} persona={false} /> : null}
      {dirty ? (
        <div className="flex justify-end gap-1.5">
          <button type="button" className={compactTextButtonClass} disabled={saving.busy} onClick={reset}>还原</button>
          <button type="button" className={compactPrimaryButtonClass} disabled={saving.busy || !valid} data-testid={`${testId}-save`}
            onClick={() => void saving.run(() => onSave(parsed ?? null))}>{saving.busy ? "保存中..." : "保存"}</button>
        </div>
      ) : null}
    </div>
  );
}
