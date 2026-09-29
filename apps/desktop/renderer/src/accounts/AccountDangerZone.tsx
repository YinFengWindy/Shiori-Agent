import { TrashIcon } from "@phosphor-icons/react";
import { confirmPersonaLines } from "../shared/mascot/mascotLines";
import { compactDangerTextButtonClass } from "../shared/styles";
import { ConfirmDialog } from "../shared/ui/ConfirmDialog";
import type { AccountSnapshot } from "@shiori/plugin-sdk";
import { accountDeletionDescription } from "./accountPresentation";
import { useAccountDeletion } from "./useAccountDeletion";

/**
 * The account detail's bottom row, after a soft divider: the plugin's
 * secondary actions (portaled into `onActionsTarget`'s element, see
 * `AccountDetailActions`) on the left, 删除账号 on the right. Deleting asks
 * for confirmation; the list reloads after every attempt and `onDeleted`
 * follows a deletion that went through.
 */
export function AccountDangerZone({ account, roleId, onChanged, onDeleted, onActionsTarget }: {
  account: AccountSnapshot;
  roleId: string;
  onChanged: () => void;
  onDeleted: () => void;
  onActionsTarget: (element: HTMLElement | null) => void;
}) {
  const deletion = useAccountDeletion(roleId, onChanged);
  return <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line-soft pt-4">
    <div ref={onActionsTarget} className="flex flex-wrap items-center gap-1" />
    <button type="button" className={compactDangerTextButtonClass} onClick={() => deletion.request(account)}>
      <TrashIcon className="h-4 w-4" aria-hidden="true" />删除账号
    </button>
    {/* Rendered inside the detail dialog so it nests as that dialog's child. */}
    <ConfirmDialog
      open={Boolean(deletion.pending)}
      title="删除账号"
      persona={confirmPersonaLines.destructive}
      description={accountDeletionDescription(deletion.pending)}
      confirmLabel="确认删除"
      busy={deletion.busy}
      error={deletion.error}
      onClose={deletion.cancel}
      onConfirm={() => void deletion.confirm().then((deleted) => { if (deleted) onDeleted(); })}
    />
  </div>;
}
