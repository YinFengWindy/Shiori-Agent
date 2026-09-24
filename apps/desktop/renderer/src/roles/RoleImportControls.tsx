import { useEffect, useState } from "react";
import { FileText, UploadSimple } from "@phosphor-icons/react";
import type React from "react";
import type { RoleCardImportState } from "../app/roleCardImportState";
import type { NewRoleFormState } from "../shared/types";
import { compactButtonSizeClass, cx, ghostButtonSurfaceClass } from "../shared/styles";
import { RoleCardImportPreviewDialog } from "./RoleCardImportPreview";
import { selectRoleCreateState } from "./roleCreateSelectors";

/** Shares import actions and preview/asset choices across both creation screens. */
export function RoleImportControls({ imported, form, disabled, onImport, onCancel, onUpdateForm }: {
  imported: RoleCardImportState;
  form: NewRoleFormState;
  disabled: boolean;
  onImport: () => void;
  onCancel: () => void;
  onUpdateForm: React.Dispatch<React.SetStateAction<NewRoleFormState>>;
}) {
  const [open, setOpen] = useState(false);
  const previewId = imported.preview?.import_id;
  useEffect(() => { if (previewId) setOpen(true); }, [previewId]);
  const { previewImagePath } = selectRoleCreateState(form, imported);
  return (
    <div className="flex items-center gap-2">
      <button type="button" data-testid="import-role-card-button" disabled={disabled || imported.status !== "idle"}
        onClick={onImport} className={cx(ghostButtonSurfaceClass, compactButtonSizeClass)}>
        <UploadSimple className="h-4 w-4" aria-hidden="true" />{imported.status === "previewing" ? "正在导入…" : "导入角色卡"}
      </button>
      {imported.preview ? <>
        <button type="button" aria-label="查看角色卡预览" title="查看角色卡预览" disabled={disabled}
          onClick={() => setOpen(true)} className={cx(ghostButtonSurfaceClass, "grid h-9 w-9 shrink-0 place-items-center")}><FileText className="h-4 w-4" aria-hidden="true" /></button>
        <RoleCardImportPreviewDialog open={open} preview={imported.preview} selections={form.emotionSelections ?? {}}
          onSelectEmotion={(name, assetId) => onUpdateForm((current) => ({ ...current, emotionSelections: { ...current.emotionSelections, [name]: assetId } }))}
          sourceUrl={previewImagePath ? window.miraDesktop.localAssetUrl(previewImagePath) : ""}
          onClose={() => setOpen(false)} onCancel={() => { setOpen(false); onCancel(); }} />
      </> : null}
    </div>
  );
}
