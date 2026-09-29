import { InlineError } from "../shared/feedback/InlineError";
import { textareaClass } from "@shiori/plugin-sdk";
import { compactPrimaryButtonClass, compactTextButtonClass } from "../shared/styles";
import type { PhoneChatInfoSectionProps } from "./PhoneChatInfoSections";
import { PhoneLoadError } from "./PhoneLoadError";
import { useBusyAction } from "../shared/useBusyAction";
import { useEditDraft } from "../shared/useEditDraft";
import { noteDraftDirty } from "./phoneChatInfo";
import { usePhoneGroupNote } from "./usePhoneChatMemory";

/** The note block's editor once the note has loaded: Markdown text, saved or reverted while it differs. */
function GroupNoteEditor({ stored, label, onSave }: {
  stored: string;
  label: string;
  onSave: (note: string) => Promise<void>;
}) {
  const { draft, dirty, setDraft, reset } = useEditDraft(stored, noteDraftDirty);
  const saving = useBusyAction();
  return (
    <div className="grid gap-1.5">
      <textarea className={textareaClass} rows={6} value={draft} aria-label={label} data-testid="phone-info-note-input"
        disabled={saving.busy} onChange={(event) => setDraft(event.target.value)} />
      {saving.error ? <InlineError message={saving.error} persona={false} /> : null}
      {dirty ? (
        <div className="flex justify-end gap-1.5">
          <button type="button" className={compactTextButtonClass} disabled={saving.busy} onClick={reset}>还原</button>
          <button type="button" className={compactPrimaryButtonClass} disabled={saving.busy} data-testid="phone-info-note-save"
            onClick={() => void saving.run(() => onSave(draft))}>{saving.busy ? "保存中..." : "保存"}</button>
        </div>
      ) : null}
    </div>
  );
}

/** 群笔记: what the role noted about the conversation, as editable Markdown. */
export function PhoneGroupNoteSection({ section, roleId, conversation }: PhoneChatInfoSectionProps) {
  const { note, error, retry, save } = usePhoneGroupNote(roleId, conversation.threadId);
  if (error) return <PhoneLoadError message={error} onRetry={() => void retry()} />;
  if (note === null) return null;
  return <GroupNoteEditor stored={note} label={section.title} onSave={save} />;
}
