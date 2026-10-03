import { useState } from "react";
import { InlineError } from "../shared/feedback/InlineError";
import { confirmPersonaLines } from "../shared/mascot/mascotLines";
import { badgeClass, cx, inputClass, textareaClass } from "@yinfengwindy/shiori-sdk";
import { compactDangerTextButtonClass, compactPrimaryButtonClass, compactTextButtonClass } from "../shared/styles";
import { ConfirmDialog } from "../shared/ui/ConfirmDialog";
import { useBusyAction } from "../shared/useBusyAction";
import { useEditDraft } from "../shared/useEditDraft";
import { memberDraftDirty, type PhoneMemberDraft } from "./phoneChatInfo";
import { PhoneInfoEmpty } from "./PhoneInfoEmpty";
import { PhoneLoadError } from "./PhoneLoadError";
import type { PhoneMember } from "./phoneMemoryClient";
import { PhoneScreenHeader } from "./PhoneScreenHeader";
import { usePhoneMemberProfile } from "./usePhoneChatMemory";

const fieldLabelClass = "grid gap-1 text-caption font-medium text-ink-muted";

/**
 * A stored profile's editor: the nickname history (read-only), the brief
 * and the full profile (editable, saved or reverted while they differ), and
 * deletion behind a confirmation.
 */
function MemberProfileEditor({ member, onSave, onDelete }: {
  member: PhoneMember;
  onSave: (fields: PhoneMemberDraft) => Promise<void>;
  onDelete: () => Promise<void>;
}) {
  const { draft, dirty, setDraft, reset } = useEditDraft(member, memberDraftDirty);
  const saving = useBusyAction();
  const deleting = useBusyAction();
  const [confirming, setConfirming] = useState(false);
  const busy = saving.busy || deleting.busy;
  return (
    <div className="grid content-start gap-3 p-3" data-testid="phone-member-profile">
      <p className="m-0 text-caption tabular-nums text-ink-muted">ID {member.senderId}</p>
      {member.nicknames.length ? (
        <div className="grid gap-1">
          <span className="text-caption font-medium text-ink-muted">昵称历史</span>
          <ul className="m-0 flex list-none flex-wrap gap-1 p-0" data-testid="phone-member-nicknames">
            {member.nicknames.map((name) => <li key={name} className={cx(badgeClass, "px-1.5 py-0")}>{name}</li>)}
          </ul>
        </div>
      ) : null}
      <label className={fieldLabelClass}>
        速记
        <input className={inputClass} value={draft.brief} disabled={busy} data-testid="phone-member-brief"
          onChange={(event) => setDraft({ ...draft, brief: event.target.value })} />
      </label>
      <label className={fieldLabelClass}>
        档案
        <textarea className={textareaClass} rows={8} value={draft.profile} disabled={busy} data-testid="phone-member-text"
          onChange={(event) => setDraft({ ...draft, profile: event.target.value })} />
      </label>
      {saving.error ? <InlineError message={saving.error} persona={false} /> : null}
      <div className="flex items-center gap-1.5">
        <button type="button" className={compactDangerTextButtonClass} disabled={busy} data-testid="phone-member-delete"
          onClick={() => { deleting.clearError(); setConfirming(true); }}>删除档案</button>
        {dirty ? (
          <>
            <button type="button" className={cx(compactTextButtonClass, "ml-auto")} disabled={busy}
              onClick={reset}>还原</button>
            <button type="button" className={compactPrimaryButtonClass} disabled={busy} data-testid="phone-member-save"
              onClick={() => void saving.run(() => onSave({ brief: draft.brief, profile: draft.profile }))}>{saving.busy ? "保存中..." : "保存"}</button>
          </>
        ) : null}
      </div>
      <ConfirmDialog
        open={confirming}
        title="删除成员档案"
        persona={confirmPersonaLines.destructive}
        description={`${member.callName}（ID ${member.senderId}）的档案将被删除；同一渠道的所有群共用这份档案。`}
        confirmLabel="确认删除"
        busy={deleting.busy}
        error={deleting.error}
        onClose={() => setConfirming(false)}
        onConfirm={() => void deleting.run(onDelete)}
      />
    </div>
  );
}

/**
 * One member's profile, opened from a chat avatar or the info page's member
 * list. Once it is deleted, the screen goes back.
 */
export function PhoneMemberProfilePage({ roleId, threadId, senderId, backLabel, onBack, onChanged }: {
  roleId: string;
  threadId: string;
  senderId: string;
  backLabel: string;
  onBack: () => void;
  /** The profile was saved or deleted, so lists showing it are stale. */
  onChanged: () => void;
}) {
  const { profile, error, retry, save, remove } = usePhoneMemberProfile(roleId, threadId, senderId);
  const member = profile?.member;
  return (
    <div className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)]">
      <PhoneScreenHeader title={member?.callName ?? "成员档案"} backLabel={backLabel} onBack={onBack} focusBack />
      <div className="surface-glass min-h-0 overflow-y-auto">
        {error ? <PhoneLoadError message={error} onRetry={() => void retry()} />
          : !profile ? null
            : !member ? <div className="p-3"><PhoneInfoEmpty label="暂无档案" /></div>
              : <MemberProfileEditor member={member}
                onSave={async (fields) => { await save(fields); onChanged(); }}
                onDelete={async () => { await remove(); onChanged(); onBack(); }} />}
      </div>
    </div>
  );
}
